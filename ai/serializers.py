from rest_framework import serializers
from .models import Conversation, Message
from django.core.validators import FileExtensionValidator

class MessageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = ['id', 'sender', 'text', 'image_url', 'created_at']
        read_only_fields = ['id', 'created_at']
    
    def get_image_url(self, obj):
        if obj.image:
            return obj.image.url
        return None

class ConversationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Conversation
        fields = ['id', 'title', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

class AudioTranscribeSerializer(serializers.Serializer):
    audio = serializers.FileField(
        validators=[FileExtensionValidator(allowed_extensions=['mp3', 'wav', 'm4a', 'webm'])]
    )

    def validate_audio(self, value):
        if value.size > 10 * 1024 * 1024:
            raise serializers.ValidationError("Audio file too large. Max 10MB.")
        return value

class ImageUploadSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'webp'])]
    )

    class Meta:
        model = Message
        fields = ['image']

    def validate_image(self, value):
        if value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError("Image file too large. Max 5MB.")
        return value