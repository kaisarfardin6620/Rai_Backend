import json
import logging
import bleach
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.core.cache import cache
from django.core.exceptions import ValidationError
from .models import Conversation, Message
from .tasks import generate_ai_response

logger = logging.getLogger(__name__)

class ChatConsumer(AsyncWebsocketConsumer):
    MAX_MESSAGE_LENGTH = 10000
    RATE_LIMIT_MESSAGES = 20
    RATE_LIMIT_WINDOW = 60
    
    async def connect(self):
        self.user = self.scope["user"]
        if self.user.is_anonymous:
            logger.warning("Anonymous user attempted WebSocket connection")
            await self.close(code=4001)
            return

        route_kwargs = self.scope['url_route'].get('kwargs', {})
        self.conversation_id = route_kwargs.get('conversation_id')

        if self.conversation_id:
            self.room_group_name = f"chat_{self.conversation_id}"
            
            exists = await self.check_conversation_exists(self.conversation_id, self.user)
            if not exists:
                logger.warning(f"User {self.user.id} tried to access non-existent conversation {self.conversation_id}")
                await self.close(code=4004)
                return

            await self.channel_layer.group_add(self.room_group_name, self.channel_name)
            await self.accept()

            history = await self.get_chat_history(self.conversation_id)
            await self.send(text_data=json.dumps({"type": "history", "messages": history}))
        else:
            await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
        logger.info(f"User {self.user.id} disconnected with code {close_code}")

    async def receive(self, text_data):
        try:
            text_data_json = json.loads(text_data)
            message_text = text_data_json.get('message', '').strip()
            
            if not message_text:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'Message cannot be empty'
                }))
                return
            
            if len(message_text) > self.MAX_MESSAGE_LENGTH:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': f'Message too long. Maximum {self.MAX_MESSAGE_LENGTH} characters.'
                }))
                return
            
            message_text = bleach.clean(message_text, tags=[], strip=True)
            
            rate_limit_key = f"chat_rate_limit_{self.user.id}"
            try:
                current_count = cache.get(rate_limit_key, 0)
                
                if current_count >= self.RATE_LIMIT_MESSAGES:
                    await self.send(text_data=json.dumps({
                        'type': 'error',
                        'message': 'Rate limit exceeded. Please wait a moment.'
                    }))
                    return
                
                cache.set(rate_limit_key, current_count + 1, self.RATE_LIMIT_WINDOW)
            except Exception as cache_error:
                logger.error(f"Cache error for user {self.user.id}: {cache_error}")
            
            if not self.conversation_id:
                self.conversation = await self.create_conversation(self.user, "New Chat")
                self.conversation_id = str(self.conversation.id)
                self.room_group_name = f"chat_{self.conversation_id}"

                await self.channel_layer.group_add(self.room_group_name, self.channel_name)

                await self.send(text_data=json.dumps({
                    "type": "init",
                    "conversation_id": self.conversation_id,
                    "title": "New Chat",
                    "message": "Conversation created."
                }))

            await self.save_message(self.conversation_id, message_text, 'user')
            message_count = await self.get_message_count(self.conversation_id)
            is_new_chat = (message_count <= 1)
            
            generate_ai_response.delay(str(self.conversation_id), message_text, self.user.id, is_new_chat)
            
            await self.send(text_data=json.dumps({
                'type': 'chat_message',
                'message': message_text,
                'sender': 'user'
            }))
            
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON from user {self.user.id}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid message format'
            }))
        except ValidationError as ve:
            logger.warning(f"Validation error for user {self.user.id}: {ve}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid input'
            }))
        except Exception as e:
            logger.error(f"Error in ChatConsumer.receive for user {self.user.id}: {e}", exc_info=True)
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'An error occurred. Please try again.'
            }))

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message': event['message'],
            'sender': event['sender']
        }))
    
    async def chat_title_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'title_updated',
            'title': event['title'],
            'conversation_id': event['conversation_id']
        }))
    
    async def chat_error(self, event):
        await self.send(text_data=json.dumps({'type': 'error', 'message': event['message']}))

    @database_sync_to_async
    def create_conversation(self, user, title):
        return Conversation.objects.create(user=user, title=title)

    @database_sync_to_async
    def check_conversation_exists(self, conv_id, user):
        return Conversation.objects.filter(id=conv_id, user=user, is_active=True).exists()

    @database_sync_to_async
    def get_chat_history(self, conv_id):
        messages = Message.objects.filter(conversation_id=conv_id).select_related('conversation').order_by('created_at')
        return [{"sender": msg.sender, "message": msg.text, "created_at": str(msg.created_at)} for msg in messages]

    @database_sync_to_async
    def save_message(self, conv_id, text, sender):
        conversation = Conversation.objects.select_for_update().get(id=conv_id)
        Message.objects.create(conversation=conversation, text=text, sender=sender)
        conversation.save(update_fields=['updated_at'])
        
        cache_key = f"messages_{conv_id}_{conversation.user_id}"
        cache.delete(cache_key)
        cache_key_conv = f"conversations_{conversation.user_id}"
        cache.delete(cache_key_conv)
    
    @database_sync_to_async
    def get_message_count(self, conv_id):
        return Message.objects.filter(conversation_id=conv_id).count()