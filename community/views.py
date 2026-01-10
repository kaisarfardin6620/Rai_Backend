from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.db.models import Count, Q
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import Community, Membership, CommunityMessage, JoinRequest
from .serializers import (
    CommunityListSerializer, CommunityDetailSerializer, CreateCommunitySerializer,
    MembershipSerializer, CommunityMessageSerializer, AddMemberSerializer,
    JoinRequestSerializer
)
from Rai_Backend.utils import api_response
from rest_framework.pagination import PageNumberPagination
from .permissions import IsCommunityAdmin

User = get_user_model()

class StandardPagination(PageNumberPagination):
    page_size = 30
    max_page_size = 100

class CommunityViewSet(viewsets.ModelViewSet):
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    pagination_class = StandardPagination

    def get_permissions(self):
        if self.action in ['update', 'partial_update', 'destroy', 'process_request', 'add_member', 'reset_invite_link']:
            return [permissions.IsAuthenticated(), IsCommunityAdmin()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        return Community.objects.filter(
            memberships__user=self.request.user
        ).annotate(member_count=Count('memberships')).order_by('-updated_at')

    def get_serializer_class(self):
        if self.action == 'list':
            return CommunityListSerializer
        if self.action == 'create':
            return CreateCommunitySerializer
        return CommunityDetailSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            with transaction.atomic():
                community = serializer.save()
                Membership.objects.create(
                    community=community,
                    user=request.user,
                    role='admin'
                )
            detail_serializer = CommunityDetailSerializer(community, context={'request': request})
            return api_response(message="Community created", data=detail_serializer.data, status_code=201, request=request)
        return api_response(message="Validation failed", data=serializer.errors, success=False, status_code=400, request=request)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        if serializer.is_valid():
            self.perform_update(serializer)
            return api_response(message="Community updated", data=serializer.data, request=request)
        return api_response(message="Validation failed", data=serializer.errors, success=False, status_code=400, request=request)

    @action(detail=True, methods=['get'])
    def join_requests(self, request, pk=None):
        community = self.get_object()
        requests = JoinRequest.objects.filter(community=community).select_related('user').order_by('-created_at')
        serializer = JoinRequestSerializer(requests, many=True, context={'request': request})
        return api_response(message="Pending requests", data=serializer.data, request=request)

    @action(detail=True, methods=['post'], url_path='process_request')
    def process_request(self, request, pk=None):
        community = self.get_object()
        request_id = request.data.get('request_id')
        action_type = request.data.get('action')

        if not request_id or not action_type:
            return api_response(message="Missing data", success=False, status_code=400, request=request)

        join_req = get_object_or_404(JoinRequest, id=request_id, community=community)

        if action_type == 'approve':
            Membership.objects.get_or_create(community=community, user=join_req.user, defaults={'role': 'member'})
            join_req.delete()
            return api_response(message="User approved", status_code=200, request=request)
        
        elif action_type == 'reject':
            join_req.delete()
            return api_response(message="User rejected", status_code=200, request=request)

        return api_response(message="Invalid action", success=False, status_code=400, request=request)

    @action(detail=False, methods=['post'], url_path='join_by_code')
    def join_by_code(self, request):
        code = request.data.get('invite_code')
        if not code:
            return api_response(message="Invite code required", success=False, status_code=400, request=request)
        try:
            community = Community.objects.get(invite_code=code)
        except Community.DoesNotExist:
            return api_response(message="Invalid invite code", success=False, status_code=404, request=request)
        
        if Membership.objects.filter(community=community, user=request.user).exists():
             return api_response(message="Already a member", data={"community_id": community.id, "name": community.name}, status_code=200, request=request)

        with transaction.atomic():
            Membership.objects.create(community=community, user=request.user, role='member')
            JoinRequest.objects.filter(community=community, user=request.user).delete()

        return api_response(message="Joined successfully", data={"community_id": community.id, "name": community.name}, status_code=200, request=request)

    @action(detail=True, methods=['post'], url_path='reset_invite_link')
    def reset_invite_link(self, request, pk=None):
        community = self.get_object()
        community.rotate_invite_code()
        serializer = CommunityDetailSerializer(community, context={'request': request})
        return api_response(message="Invite link reset", data={"invite_code": community.invite_code, "invite_link": serializer.data['invite_link']}, request=request)

    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        community = get_object_or_404(Community, pk=pk)
        if not Membership.objects.filter(community=community, user=request.user).exists():
            return api_response(message="Not a member", success=False, status_code=403, request=request)
        
        msgs = CommunityMessage.objects.filter(community=community).select_related('sender').order_by('-created_at')
        paginator = StandardPagination()
        page = paginator.paginate_queryset(msgs, request)
        serializer = CommunityMessageSerializer(page, many=True, context={'request': request})
        data = list(reversed(serializer.data))
        return api_response(message="Messages fetched", data=data, request=request)

    @action(detail=True, methods=['post'])
    def join(self, request, pk=None):
        try:
            community = Community.objects.get(pk=pk)
        except Community.DoesNotExist:
            return api_response(message="Community not found", success=False, status_code=404, request=request)

        if Membership.objects.filter(community=community, user=request.user).exists():
             return api_response(message="Already a member", success=False, status_code=400, request=request)

        if community.is_private:
            JoinRequest.objects.get_or_create(community=community, user=request.user)
            return api_response(message="Join request sent", status_code=200, request=request)
        else:
            Membership.objects.create(community=community, user=request.user, role='member')
            return api_response(message="Joined successfully", status_code=200, request=request)

    @action(detail=True, methods=['post'])
    def leave(self, request, pk=None):
        community = get_object_or_404(Community, pk=pk)
        Membership.objects.filter(community=community, user=request.user).delete()
        if community.memberships.count() == 0:
            community.delete()
        return api_response(message="Left community", status_code=200, request=request)

    @action(detail=True, methods=['post'])
    def toggle_mute(self, request, pk=None):
        community = get_object_or_404(Community, pk=pk)
        try:
            membership = Membership.objects.get(community=community, user=request.user)
            membership.is_muted = not membership.is_muted
            membership.save()
            return api_response(message="Mute status updated", data={"is_muted": membership.is_muted}, request=request)
        except Membership.DoesNotExist:
            return api_response(message="Not a member", success=False, status_code=403, request=request)

    @action(detail=True, methods=['get'])
    def members(self, request, pk=None):
        community = get_object_or_404(Community, pk=pk)
        if not Membership.objects.filter(community=community, user=request.user).exists():
            return api_response(message="Access denied", success=False, status_code=403, request=request)

        search = request.query_params.get('search', '').strip()
        memberships = Membership.objects.filter(community=community).select_related('user')
        if search:
            memberships = memberships.filter(Q(user__username__icontains=search) | Q(user__first_name__icontains=search))

        paginator = StandardPagination()
        page = paginator.paginate_queryset(memberships, request)
        serializer = MembershipSerializer(page, many=True, context={'request': request})
        return api_response(message="Members fetched", data=serializer.data, request=request)

    @action(detail=True, methods=['post'])
    def add_member(self, request, pk=None):
        community = self.get_object()
        serializer = AddMemberSerializer(data=request.data)
        if serializer.is_valid():
            query = serializer.validated_data['username_or_email']
            try:
                user_to_add = User.objects.get(Q(username=query) | Q(email=query))
                if Membership.objects.filter(community=community, user=user_to_add).exists():
                    return api_response(message="User already in group", success=False, status_code=400, request=request)
                
                Membership.objects.create(community=community, user=user_to_add, role='member')
                JoinRequest.objects.filter(community=community, user=user_to_add).delete()
                return api_response(message="Member added", status_code=200, request=request)
            except User.DoesNotExist:
                return api_response(message="User not found", success=False, status_code=404, request=request)
        return api_response(message="Invalid data", success=False, status_code=400, request=request)

    @action(detail=True, methods=['post'], url_path='upload-media')
    def upload_media(self, request, pk=None):
        community = get_object_or_404(Community, pk=pk)
        if not Membership.objects.filter(community=community, user=request.user).exists():
             return api_response(message="Not a member", success=False, status_code=403, request=request)
        
        image = request.FILES.get('image')
        audio = request.FILES.get('audio')
        
        if not image and not audio:
             return api_response(message="No media provided", success=False, status_code=400, request=request)
        
        msg = CommunityMessage.objects.create(
            community=community, 
            sender=request.user, 
            image=image, 
            audio=audio, 
            text=""
        )
        
        image_url = request.build_absolute_uri(msg.image.url) if msg.image else None
        audio_url = request.build_absolute_uri(msg.audio.url) if msg.audio else None
        
        profile_pic_url = None
        if request.user.profile_picture:
            profile_pic_url = request.build_absolute_uri(request.user.profile_picture.url)

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"community_{community.id}",
            {
                'type': 'chat_message',
                'id': str(msg.id),
                'message': msg.text,
                'image': image_url,
                'audio': audio_url,
                'sender': {
                    'id': request.user.id,
                    'username': request.user.username,
                    'first_name': request.user.first_name,
                    'last_name': request.user.last_name,
                    'profile_picture': profile_pic_url
                },
                'created_at': str(msg.created_at)
            }
        )
        
        return api_response(
            message="Media uploaded", 
            data={"image_url": image_url, "audio_url": audio_url, "message_id": str(msg.id)}, 
            request=request
        )