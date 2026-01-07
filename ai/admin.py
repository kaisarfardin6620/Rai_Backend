from django.contrib import admin
from .models import Conversation, Message

class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ("sender", "text", "created_at")
    ordering = ("created_at",)

@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "title", "is_active", "created_at", "updated_at")
    list_filter = ("is_active", "created_at", "updated_at")
    search_fields = ("title", "user__username")
    inlines = [MessageInline]
    ordering = ("-updated_at",)

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "sender", "text", "created_at")
    list_filter = ("sender", "created_at")
    search_fields = ("text", "conversation__title", "conversation__user__username")
    ordering = ("created_at",)