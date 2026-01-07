from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import UserRateThrottle
from rest_framework.pagination import PageNumberPagination
from rest_framework import status
from django.core.cache import cache
from django.db.models import Prefetch
from Rai_Backend.utils import api_response
from .models import Conversation, Message
from .serializers import ConversationSerializer, MessageSerializer
import logging

logger = logging.getLogger(__name__)

class StandardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

class ConversationThrottle(UserRateThrottle):
    rate = '100/hour'

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@throttle_classes([ConversationThrottle])
def get_conversations(request):
    try:
        cache_key = f"conversations_{request.user.id}"
        cached_data = cache.get(cache_key)
        
        if cached_data:
            return api_response(
                message="History fetched",
                data=cached_data,
                request=request
            )
        
        conversations = Conversation.objects.filter(
            user=request.user,
            is_active=True
        ).select_related('user').order_by('-updated_at')
        
        paginator = StandardPagination()
        paginated_conversations = paginator.paginate_queryset(conversations, request)
        serializer = ConversationSerializer(paginated_conversations, many=True)
        
        cache.set(cache_key, serializer.data, 300)
        
        return api_response(
            message="History fetched",
            data=serializer.data,
            request=request
        )
    except Conversation.DoesNotExist:
        return api_response(
            message="No conversations found",
            data=[],
            request=request
        )
    except Exception as e:
        logger.error(f"Error fetching conversations for user {request.user.id}: {e}", exc_info=True)
        return api_response(
            message="Failed to fetch conversations",
            success=False,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            request=request
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@throttle_classes([ConversationThrottle])
def get_messages(request, conversation_id):
    try:
        try:
            conversation = Conversation.objects.select_related('user').get(
                id=conversation_id,
                user=request.user,
                is_active=True
            )
        except (Conversation.DoesNotExist, ValueError):
            return api_response(
                message="Not found",
                success=False,
                status_code=status.HTTP_404_NOT_FOUND,
                request=request
            )

        cache_key = f"messages_{conversation_id}_{request.user.id}"
        cached_data = cache.get(cache_key)
        
        if cached_data:
            return api_response(
                message="Messages fetched",
                data=cached_data,
                request=request
            )

        messages = Message.objects.filter(conversation=conversation).order_by('created_at')
        
        paginator = StandardPagination()
        paginated_messages = paginator.paginate_queryset(messages, request)
        serializer = MessageSerializer(paginated_messages, many=True)
        
        cache.set(cache_key, serializer.data, 60)
        
        return api_response(
            message="Messages fetched",
            data=serializer.data,
            request=request
        )
    except Exception as e:
        logger.error(f"Error fetching messages for conversation {conversation_id}: {e}", exc_info=True)
        return api_response(
            message="Failed to fetch messages",
            success=False,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            request=request
        )

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
@throttle_classes([ConversationThrottle])
def delete_conversation(request, conversation_id):
    try:
        try:
            conversation = Conversation.objects.get(
                id=conversation_id,
                user=request.user,
                is_active=True
            )
        except (Conversation.DoesNotExist, ValueError):
            return api_response(
                message="Conversation not found or access denied.",
                success=False,
                status_code=status.HTTP_404_NOT_FOUND,
                request=request
            )
        
        conversation.delete()
        
        cache_key = f"conversations_{request.user.id}"
        cache.delete(cache_key)
        
        return api_response(
            message="Conversation deleted successfully.",
            status_code=status.HTTP_200_OK,
            request=request
        )
    except Exception as e:
        logger.error(f"Error deleting conversation {conversation_id}: {e}", exc_info=True)
        return api_response(
            message="Failed to delete conversation",
            success=False,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            request=request
        )