from rest_framework import serializers
from .models import Community, Membership, CommunityMessage, JoinRequest
from django.contrib.auth import get_user_model
from django.core.validators import FileExtensionValidator

User = get_user_model()

class UserShortSerializer(serializers.ModelSerializer):
    profile_picture = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'profile_picture']

    def get_profile_picture(self, obj):
        if obj.profile_picture:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.profile_picture.url)
            return obj.profile_picture.url
        return None

class JoinRequestSerializer(serializers.ModelSerializer):
    user = UserShortSerializer(read_only=True)
    class Meta:
        model = JoinRequest
        fields = ['id', 'user', 'created_at']

class CommunityListSerializer(serializers.ModelSerializer):
    member_count = serializers.IntegerField(read_only=True)
    icon = serializers.SerializerMethodField()
    
    class Meta:
        model = Community
        fields = ['id', 'name', 'icon', 'member_count', 'updated_at']
        read_only_fields = ['icon']

    def get_icon(self, obj):
        if obj.icon:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.icon.url)
            return obj.icon.url
        return None

class MembershipSerializer(serializers.ModelSerializer):
    user = UserShortSerializer(read_only=True)
    
    class Meta:
        model = Membership
        fields = ['id', 'user', 'role', 'is_muted', 'joined_at']

class CommunityDetailSerializer(serializers.ModelSerializer):
    icon = serializers.SerializerMethodField()
    is_member = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()
    is_muted = serializers.SerializerMethodField()
    member_count = serializers.SerializerMethodField()
    invite_link = serializers.SerializerMethodField()
    pending_request_count = serializers.SerializerMethodField()

    class Meta:
        model = Community
        fields = [
            'id', 'name', 'description', 'icon', 'is_private', 
            'invite_code', 'invite_link', 'created_at', 'member_count', 
            'is_member', 'role', 'is_muted', 'pending_request_count'
        ]
        read_only_fields = ['invite_code', 'invite_link', 'created_at']

    def get_icon(self, obj):
        if obj.icon:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.icon.url)
            return obj.icon.url
        return None

    def get_member_count(self, obj):
        return obj.memberships.count()

    def get_is_member(self, obj):
        user = self.context['request'].user
        return Membership.objects.filter(community=obj, user=user).exists()

    def get_role(self, obj):
        user = self.context['request'].user
        try:
            return Membership.objects.get(community=obj, user=user).role
        except Membership.DoesNotExist:
            return None

    def get_is_muted(self, obj):
        user = self.context['request'].user
        try:
            return Membership.objects.get(community=obj, user=user).is_muted
        except Membership.DoesNotExist:
            return False

    def get_invite_link(self, obj):
        request = self.context.get('request')
        if request:
            return f"{request.scheme}://{request.get_host()}/join/{obj.invite_code}"
        return f"/join/{obj.invite_code}"

    def get_pending_request_count(self, obj):
        user = self.context['request'].user
        is_admin = Membership.objects.filter(community=obj, user=user, role='admin').exists()
        if is_admin:
            return obj.join_requests.count()
        return 0

class CommunityMessageSerializer(serializers.ModelSerializer):
    sender = UserShortSerializer(read_only=True)
    image = serializers.SerializerMethodField()

    class Meta:
        model = CommunityMessage
        fields = ['id', 'community', 'sender', 'text', 'image', 'created_at']
        read_only_fields = ['id', 'created_at', 'sender', 'image']

    def get_image(self, obj):
        if obj.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None

class CreateCommunitySerializer(serializers.ModelSerializer):
    icon = serializers.ImageField(
        required=False, 
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'webp'])]
    )

    class Meta:
        model = Community
        fields = ['name', 'description', 'icon', 'is_private']

    def validate_icon(self, value):
        if value and value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError("Icon size cannot exceed 5MB.")
        return value

class AddMemberSerializer(serializers.Serializer):
    username_or_email = serializers.CharField()