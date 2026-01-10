import json
import logging
import re
import unicodedata
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.core.cache import cache
from .models import Conversation, Message
from .tasks import generate_ai_response
from django.conf import settings

logger = logging.getLogger(__name__)

DANGEROUS_PATTERNS = [
    re.compile(r'ignore\s+(previous|all|prior)\s+instructions', re.IGNORECASE),
    re.compile(r'system:\s*you\s+are', re.IGNORECASE),
    re.compile(r'new\s+instructions:', re.IGNORECASE),
    re.compile(r'<\|im_start\|>', re.IGNORECASE),
    re.compile(r'<\|im_end\|>', re.IGNORECASE),
]

def sanitize_message(text):
    if not text: return ""
    text = ''.join(
        char for char in text 
        if unicodedata.category(char)[0] != 'C' or char in '\n\t'
    )
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def validate_user_input(text):
    if not text: return True
    for pattern in DANGEROUS_PATTERNS:
        if pattern.search(text):
            return False
    return True

class ChatConsumer(AsyncWebsocketConsumer):
    MAX_MESSAGE_LENGTH = 10000
    RATE_LIMIT_MESSAGES = settings.AI_CHAT_MAX_MESSAGES
    RATE_LIMIT_WINDOW = settings.AI_CHAT_WINDOW_SECONDS
    
    async def connect(self):
        self.user = self.scope["user"]
        if self.user.is_anonymous:
            await self.close(code=4001)
            return

        route_kwargs = self.scope['url_route'].get('kwargs', {})
        self.conversation_id = route_kwargs.get('conversation_id')
        headers = dict(self.scope['headers'])
        host = headers.get(b'host', b'').decode('utf-8')
        scheme = "https" if self.scope.get('scheme') in ['wss', 'https'] else "http"
        self.base_url = f"{scheme}://{host}"

        if self.conversation_id:
            self.room_group_name = f"chat_{self.conversation_id}"
            exists = await self.check_conversation_exists(self.conversation_id, self.user)
            if not exists:
                await self.close(code=4004)
                return

            await self.channel_layer.group_add(self.room_group_name, self.channel_name)
            await self.accept()
            history = await self.get_chat_history(self.conversation_id, self.base_url)
            await self.send(text_data=json.dumps({"type": "history", "messages": history}))
        else:
            await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_text = data.get('message', '').strip()
            image_id = data.get('image_id')
            
            if not message_text and not image_id:
                return
            
            if len(message_text) > self.MAX_MESSAGE_LENGTH:
                await self.send_json({'type': 'error', 'message': 'Message too long'})
                return
            
            message_text = sanitize_message(message_text)
            if not validate_user_input(message_text):
                await self.send_json({'type': 'error', 'message': 'Prohibited content'})
                return
            
            rate_limit_key = f"chat_limit_{self.user.id}"
            if cache.get(rate_limit_key, 0) >= self.RATE_LIMIT_MESSAGES:
                await self.send_json({'type': 'error', 'message': 'Rate limit exceeded'})
                return
            cache.set(rate_limit_key, cache.get(rate_limit_key, 0) + 1, self.RATE_LIMIT_WINDOW)
            
            if not self.conversation_id:
                self.conversation = await self.create_conversation(self.user, "New Chat")
                self.conversation_id = str(self.conversation.id)
                self.room_group_name = f"chat_{self.conversation_id}"
                await self.channel_layer.group_add(self.room_group_name, self.channel_name)
                await self.send_json({"type": "init", "conversation_id": self.conversation_id})

            if image_id:
                image_valid = await self.validate_image_ownership(image_id, self.conversation_id, self.user.id)
                if not image_valid:
                    await self.send_json({'type': 'error', 'message': 'Invalid image'})
                    return

            try:
                await self.save_message(self.conversation_id, message_text, 'user', image_id)
                message_count = await self.get_message_count(self.conversation_id)
                is_new_chat = (message_count <= 1)
            except Exception as e:
                logger.error(f"Save error: {e}")
                await self.send_json({'type': 'error', 'message': 'Failed to save'})
                return
            
            generate_ai_response.delay(str(self.conversation_id), message_text, self.user.id, is_new_chat, image_id)
            
            await self.send_json({
                'type': 'chat_message',
                'message': message_text,
                'sender': 'user',
                'image_id': image_id
            })
            
        except json.JSONDecodeError:
            pass
        except Exception as e:
            logger.error(f"Receive error: {e}", exc_info=True)

    async def send_json(self, content):
        await self.send(text_data=json.dumps(content))

    async def chat_message(self, event):
        await self.send_json({
            'type': 'chat_message',
            'message': event['message'],
            'sender': event['sender']
        })
    
    async def chat_title_update(self, event):
        await self.send_json({'type': 'title_updated', 'title': event['title']})
    
    async def chat_error(self, event):
        await self.send_json({'type': 'error', 'message': event['message']})

    @database_sync_to_async
    def create_conversation(self, user, title):
        return Conversation.objects.create(user=user, title=title)

    @database_sync_to_async
    def check_conversation_exists(self, conv_id, user):
        return Conversation.objects.filter(id=conv_id, user=user, is_active=True).exists()

    @database_sync_to_async
    def validate_image_ownership(self, image_id, conv_id, user_id):
        try:
            msg = Message.objects.select_related('conversation').get(
                id=image_id,
                conversation_id=conv_id,
                conversation__user_id=user_id,
                image__isnull=False
            )
            return True
        except Message.DoesNotExist:
            return False

    @database_sync_to_async
    def get_chat_history(self, conv_id, base_url):
        messages = Message.objects.filter(conversation_id=conv_id).order_by('-created_at')[:50]
        return [{
            "sender": m.sender, 
            "message": m.text, 
            "image_url": f"{base_url}{m.image.url}" if m.image else None,
            "created_at": str(m.created_at)
        } for m in reversed(messages)]

    @database_sync_to_async
    def save_message(self, conv_id, text, sender, image_id=None):
        from django.db import transaction
        with transaction.atomic():
            conversation = Conversation.objects.select_for_update().get(id=conv_id)
            if image_id:
                msg = Message.objects.get(id=image_id, conversation_id=conv_id)
                msg.text = text
                msg.save()
            else:
                Message.objects.create(conversation=conversation, text=text, sender=sender)
            conversation.save(update_fields=['updated_at'])
            cache.delete(f"conversations_{conversation.user_id}")

    @database_sync_to_async
    def get_message_count(self, conv_id):
        return Message.objects.filter(conversation_id=conv_id).count()