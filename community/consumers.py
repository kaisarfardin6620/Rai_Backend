import json
import structlog
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import Community, Membership, CommunityMessage

logger = structlog.get_logger(__name__)

class CommunityConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        
        if self.user.is_anonymous:
            await self.close(code=4001)
            return

        self.community_id = self.scope['url_route']['kwargs']['community_id']
        self.room_group_name = f"community_{self.community_id}"
        
        is_member = await self.check_membership(self.community_id, self.user)
        if not is_member:
            logger.warning("unauthorized_community_access", user_id=self.user.id, community_id=self.community_id)
            await self.close(code=4003)
            return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

                                  
        headers = dict(self.scope['headers'])
        host = headers.get(b'host', b'').decode('utf-8')
        scheme = "https" if self.scope.get('scheme') in ['wss', 'https'] else "http"
        self.base_url = f"{scheme}://{host}"

                      
        history = await self.get_chat_history(self.community_id, self.base_url)
        await self.send(text_data=json.dumps({"type": "history", "messages": history}))

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_text = data.get('message', '').strip()
            
            if not message_text: 
                return
            
            saved_msg = await self.save_message(self.community_id, self.user, message_text)
            
            profile_pic = None
            if self.user.profile_picture:
                profile_pic = f"{self.base_url}{self.user.profile_picture.url}"

                       
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'id': str(saved_msg.id),
                    'message': saved_msg.text,
                    'image': None,
                    'audio': None,
                    'sender': {
                        'id': self.user.id,
                        'username': self.user.username,
                        'profile_picture': profile_pic
                    },
                    'created_at': str(saved_msg.created_at)
                }
            )
        except Exception as e:
            logger.error("community_ws_error", error=str(e))

    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event))

    @database_sync_to_async
    def check_membership(self, community_id, user):
        return Membership.objects.filter(community_id=community_id, user=user).exists()

    @database_sync_to_async
    def save_message(self, community_id, user, text):
        community = Community.objects.get(id=community_id)
        msg = CommunityMessage.objects.create(community=community, sender=user, text=text)
        community.save(update_fields=['updated_at']) 
        return msg

    @database_sync_to_async
    def get_chat_history(self, community_id, base_url):
        messages = CommunityMessage.objects.filter(
            community_id=community_id
        ).select_related('sender').order_by('-created_at')[:50]
        
        return [
            {
                "id": str(m.id),
                "message": m.text,
                "image": f"{base_url}{m.image.url}" if m.image else None,
                "audio": f"{base_url}{m.audio.url}" if m.audio else None,
                "sender": {
                    "id": m.sender.id,
                    "username": m.sender.username,
                    "profile_picture": f"{base_url}{m.sender.profile_picture.url}" if m.sender.profile_picture else None
                },
                "created_at": str(m.created_at)
            }
            for m in reversed(messages)
        ]