from rest_framework.decorators import api_view, permission_classes, throttle_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.pagination import PageNumberPagination
from rest_framework import status
from django.core.cache import cache
from django.conf import settings
from Rai_Backend.utils import api_response
from .models import Conversation, Message
from .serializers import (
    ConversationSerializer, MessageSerializer, 
    AudioTranscribeSerializer, ImageUploadSerializer
)
from openai import OpenAI
import logging
import os
import tempfile

logger = logging.getLogger(__name__)

class StandardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@throttle_classes([ScopedRateThrottle])
def get_conversations(request):
    try:
        cache_key = f"conversations_{request.user.id}"
        cached_data = cache.get(cache_key)
        
        if cached_data:
            return api_response(message="History fetched", data=cached_data, request=request)
        
        conversations = Conversation.objects.filter(
            user=request.user, is_active=True
        ).select_related('user').order_by('-updated_at')
        
        paginator = StandardPagination()
        paginated_conversations = paginator.paginate_queryset(conversations, request)
        serializer = ConversationSerializer(paginated_conversations, many=True)
        
        cache.set(cache_key, serializer.data, 300)
        
        return api_response(message="History fetched", data=serializer.data, request=request)
    except Exception as e:
        logger.error(f"Error fetching conversations: {e}", exc_info=True)
        return api_response(message="Failed to fetch conversations", success=False, status_code=500, request=request)
get_conversations.throttle_scope = 'conversation'

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@throttle_classes([ScopedRateThrottle])
def get_messages(request, conversation_id):
    try:
        conversation = Conversation.objects.get(id=conversation_id, user=request.user, is_active=True)
        messages = Message.objects.filter(conversation=conversation).order_by('created_at')
        
        paginator = StandardPagination()
        paginated_messages = paginator.paginate_queryset(messages, request)
        serializer = MessageSerializer(paginated_messages, many=True)
        
        return api_response(message="Messages fetched", data=serializer.data, request=request)
    except Conversation.DoesNotExist:
        return api_response(message="Not found", success=False, status_code=404, request=request)
    except Exception as e:
        logger.error(f"Error fetching messages: {e}", exc_info=True)
        return api_response(message="Failed to fetch messages", success=False, status_code=500, request=request)
get_messages.throttle_scope = 'conversation'

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
@throttle_classes([ScopedRateThrottle])
def delete_conversation(request, conversation_id):
    try:
        conversation = Conversation.objects.get(id=conversation_id, user=request.user, is_active=True)
        conversation.delete()
        cache.delete(f"conversations_{request.user.id}")
        return api_response(message="Deleted successfully", status_code=200, request=request)
    except Conversation.DoesNotExist:
        return api_response(message="Not found", success=False, status_code=404, request=request)
delete_conversation.throttle_scope = 'conversation'

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([ScopedRateThrottle])
@parser_classes([MultiPartParser, FormParser])
def transcribe_audio(request):
    temp_path = None
    try:
        serializer = AudioTranscribeSerializer(data=request.data)
        if not serializer.is_valid():
            return api_response(message="Invalid file", data=serializer.errors, success=False, status_code=400, request=request)

        audio_file = serializer.validated_data['audio']
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(audio_file.name)[1]) as tmp_file:
            temp_path = tmp_file.name
            for chunk in audio_file.chunks():
                tmp_file.write(chunk)

        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        with open(temp_path, "rb") as file_stream:
            transcript = client.audio.transcriptions.create(
                model="whisper-1", 
                file=file_stream
            )
        
        return api_response(message="Transcribed", data={"text": transcript.text}, request=request)

    except Exception as e:
        logger.error(f"Transcription error: {e}", exc_info=True)
        return api_response(message="Transcription failed", success=False, status_code=500, request=request)
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception as e:
                logger.error(f"Failed to cleanup temp file {temp_path}: {e}")
transcribe_audio.throttle_scope = 'media'

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([ScopedRateThrottle])
@parser_classes([MultiPartParser, FormParser])
def upload_chat_image(request):
    try:
        serializer = ImageUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return api_response(message="Invalid image", data=serializer.errors, success=False, status_code=400, request=request)
        
        conversation_id = request.data.get('conversation_id')
        if not conversation_id:
            return api_response(message="Conversation ID required", success=False, status_code=400, request=request)

        try:
            conv = Conversation.objects.get(id=conversation_id, user=request.user, is_active=True)
            message = Message.objects.create(
                conversation=conv,
                sender='user',
                text='',
                image=serializer.validated_data['image']
            )
            return api_response(message="Image uploaded", data={"image_id": message.id, "url": message.image.url}, request=request)
        except Conversation.DoesNotExist:
            return api_response(message="Conversation not found", success=False, status_code=404, request=request)

    except Exception as e:
        logger.error(f"Image upload error: {e}", exc_info=True)
        return api_response(message="Upload failed", success=False, status_code=500, request=request)
upload_chat_image.throttle_scope = 'media'