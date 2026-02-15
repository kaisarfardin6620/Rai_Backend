import json
import structlog
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.conf import settings
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

            if not self.conversation_id:
                conversation = await self.create_new_conversation(self.user)
                self.conversation_id = str(conversation.id)
                self.room_group_name = f"chat_{self.conversation_id}"
                await self.channel_layer.group_add(self.room_group_name, self.channel_name)
                await self.send_json({"type": "init", "conversation_id": self.conversation_id})

            await self.save_message(self.conversation_id, message_text, 'user', image_id)

            await self.send_json({
                'type': 'chat_message',
                'message': message_text,
                'sender': 'user',
                'image_id': image_id
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
    def check_conversation_exists(self, conv_id, user):
        from .models import Conversation
        return Conversation.objects.filter(id=conv_id, user=user, is_active=True).exists()

    @database_sync_to_async
    def create_new_conversation(self, user):
        return AIService.create_conversation(user)

    @database_sync_to_async
    def save_message(self, conv_id, text, sender, image_id):
        return AIService.save_message(conv_id, text, sender, image_id)

    @database_sync_to_async
    def get_message_count(self, conv_id):
        from .models import Message
        return Message.objects.filter(conversation_id=conv_id).count()