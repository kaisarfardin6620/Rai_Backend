import json
import structlog
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.core.cache import cache
from .tasks import generate_ai_response
from .services import AIService

logger = structlog.get_logger(__name__)

class ChatConsumer(AsyncWebsocketConsumer):
    
    async def connect(self):
        self.user = self.scope["user"]
        
        if self.user.is_anonymous:
            await self.close(code=4001)
            return

        self.conversation_id = self.scope['url_route']['kwargs'].get('conversation_id')
        
        if self.conversation_id:
            self.room_group_name = f"chat_{self.conversation_id}"
            
            exists = await self.check_conversation_exists(self.conversation_id, self.user)
            if not exists:
                await self.close(code=4004)
                return

            await self.channel_layer.group_add(self.room_group_name, self.channel_name)
            await self.accept()
            history = await self.get_chat_history(self.conversation_id)
            await self.send_json({
                "type": "chat_history",
                "conversation_id": self.conversation_id,
                "messages": history
            })
        else:
            await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'conversation_id') and self.conversation_id:
            has_processing = await self.check_processing_messages(self.conversation_id)
            if not has_processing:
                lock_key = f"ai_processing_lock:{self.conversation_id}:{self.user.id}"
                await database_sync_to_async(cache.delete)(lock_key)

        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_text = data.get('message', '').strip()
            image_id = data.get('image_id')
            
            if not message_text and not image_id:
                return

            if not self.conversation_id:
                conversation = await self.create_new_conversation(self.user)
                self.conversation_id = str(conversation.id)
                self.room_group_name = f"chat_{self.conversation_id}"
                await self.channel_layer.group_add(self.room_group_name, self.channel_name)

            lock_key = f"ai_processing_lock:{self.conversation_id}:{self.user.id}"
            has_processing = await self.check_processing_messages(self.conversation_id)
            if not has_processing:
                await database_sync_to_async(cache.delete)(lock_key)

            if not await self.acquire_lock(lock_key, 35):
                await self.send_json({
                    'type': 'error',
                    'code': 'ai_busy', 
                    'message': 'AI is thinking. Please wait.'
                })
                return

            msg = await self.save_message(self.conversation_id, message_text, 'user', image_id)

            await self.send_json({
                'type': 'new_message',
                'conversation_id': self.conversation_id,
                'message': {
                    'id': msg.id,
                    'text': msg.text,
                    'sender': msg.sender,
                    'is_ai': False,
                    'status': msg.status,
                    'image_id': image_id,
                    'created_at': str(msg.created_at)
                }
            })

            is_new_chat = (await self.get_message_count(self.conversation_id)) <= 1
            
            generate_ai_response.delay(
                str(self.conversation_id), 
                message_text, 
                self.user.id, 
                is_new_chat, 
                image_id
            )
            
        except json.JSONDecodeError:
            pass
        except Exception as e:
            logger.error("ws_receive_error", error=str(e))
            await self.send_json({'type': 'error', 'message': 'System error'})

    async def send_json(self, content):
        await self.send(text_data=json.dumps(content))

    async def message_update(self, event):
        await self.send_json({
            'type': 'message_update',
            'conversation_id': event['conversation_id'],
            'message': event['message']
        })
    
    async def chat_title_update(self, event):
        await self.send_json({'type': 'title_updated', 'title': event['title']})
    
    async def chat_error(self, event):
        await self.send_json({'type': 'error', 'message': event['message']})

    @database_sync_to_async
    def acquire_lock(self, key, timeout):
        return cache.add(key, "true", timeout)

    @database_sync_to_async
    def check_processing_messages(self, conv_id):
        from .models import Message
        return Message.objects.filter(conversation_id=conv_id, status='processing').exists()

    @database_sync_to_async
    def check_conversation_exists(self, conv_id, user):
        from .models import Conversation
        return Conversation.objects.filter(id=conv_id, user=user, is_active=True).exists()

    @database_sync_to_async
    def create_new_conversation(self, user):
        return AIService.create_conversation(user)

    @database_sync_to_async
    def save_message(self, conv_id, text, sender, image_id):
        from .models import Message
        conversation_id = conv_id
        if image_id:
            msg = Message.objects.get(id=image_id, conversation_id=conversation_id)
            msg.text = text
            msg.status = 'completed'
            msg.save(update_fields=['text', 'status'])
            return msg
        else:
            return Message.objects.create(
                conversation_id=conversation_id, 
                text=text, 
                sender=sender,
                status='completed'
            )

    @database_sync_to_async
    def get_message_count(self, conv_id):
        from .models import Message
        return Message.objects.filter(conversation_id=conv_id).count()

    @database_sync_to_async
    def get_chat_history(self, conv_id):
        from .models import Message
        messages = Message.objects.filter(conversation_id=conv_id).order_by('created_at')
        return[
            {
                "id": m.id,
                "text": m.text,
                "sender": m.sender,
                "is_ai": m.sender == 'ai',
                "status": m.status,
                "image_id": m.id if m.image else None,
                "created_at": str(m.created_at)
            }
            for m in messages
        ]