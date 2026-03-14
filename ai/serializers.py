from rest_framework import serializers
from .models import Conversation, Message
from drf_spectacular.utils import extend_schema_field

class MessageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields =['id', 'sender', 'text', 'image_url', 'status', 'created_at'] 
        read_only_fields = ['id', 'created_at']
    
    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_image_url(self, obj):
        if obj.image:
            url = obj.image.url
            if url.startswith('http'):
                return url
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(url)
            from django.conf import settings
            return f"{settings.SERVER_BASE_URL}{url}"
        return None

class ConversationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Conversation
        fields =['id', 'title', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

class AudioTranscribeSerializer(serializers.Serializer):
    audio = serializers.FileField()

    def validate_audio(self, value):
        if value.size > 10 * 1024 * 1024:
            raise serializers.ValidationError("Audio file too large. Max 10MB.")
        return value

class ImageUploadSerializer(serializers.ModelSerializer):
    image = serializers.ImageField()

    class Meta:
        model = Message
        fields = ['image']

    def validate_image(self, value):
        if value.size > 50 * 1024 * 1024:
            raise serializers.ValidationError("Image file too large. Max 50MB.")
        return value