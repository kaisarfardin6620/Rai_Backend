from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from Rai_Backend.utils import api_response
from .models import Conversation, Message
from .serializers import ConversationSerializer, MessageSerializer

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_conversations(request):
    conversations = Conversation.objects.filter(user=request.user).order_by('-updated_at')
    serializer = ConversationSerializer(conversations, many=True)
    return api_response(
        message="History fetched",
        data=serializer.data,
        request=request
    )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_messages(request, conversation_id):
    try:
        conversation = Conversation.objects.get(id=conversation_id, user=request.user)
    except Conversation.DoesNotExist:
        return api_response(message="Not found", success=False, status_code=404)

    messages = Message.objects.filter(conversation=conversation).order_by('created_at')
    serializer = MessageSerializer(messages, many=True)
    return api_response(
        message="Messages fetched",
        data=serializer.data,
        request=request
    )

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_conversation(request, conversation_id):
    try:
        conversation = Conversation.objects.get(id=conversation_id, user=request.user)
        conversation.delete()
        
        return api_response(
            message="Conversation deleted successfully.",
            status_code=status.HTTP_200_OK,
            request=request
        )
    except Conversation.DoesNotExist:
        return api_response(
            message="Conversation not found or access denied.",
            success=False,
            status_code=status.HTTP_404_NOT_FOUND,
            request=request
        )