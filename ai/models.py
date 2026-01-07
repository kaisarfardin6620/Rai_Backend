from django.db import models
from django.conf import settings
from django.core.validators import MaxLengthValidator
import uuid

class Conversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="conversations", db_index=True)
    title = models.CharField(max_length=255, blank=True, db_index=True) 
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['user', '-updated_at']),
            models.Index(fields=['user', 'is_active']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.title}"
    def __repr__(self):
        return f"<Conversation {self.id}: {self.title}>"

class Message(models.Model):
    SENDER_CHOICES = (
        ('user', 'User'),
        ('ai', 'AI'),
    )
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages", db_index=True)
    sender = models.CharField(max_length=10, choices=SENDER_CHOICES, db_index=True)
    text = models.TextField(validators=[MaxLengthValidator(50000)])
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['conversation', 'created_at']),
            models.Index(fields=['conversation', 'sender']),
        ]
    
    def __repr__(self):
        return f"<Message {self.id}: {self.sender} in {self.conversation_id}>"