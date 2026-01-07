from celery import shared_task
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.conf import settings
from django.core.cache import cache
from openai import OpenAI
from .models import Conversation, Message
from tiktoken import encoding_for_model
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def generate_ai_response(self, conversation_id, user_text, user_id, is_new_chat=False):
    channel_layer = get_channel_layer()
    group_name = f"chat_{conversation_id}"
    client = OpenAI(api_key=settings.OPENAI_API_KEY, timeout=30.0)
    
    MAX_CONTEXT_TOKENS = 8000
    
    try:
        conversation = Conversation.objects.select_related('user').get(id=conversation_id)
        
        if is_new_chat:
            try:
                title_response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "Generate a 3-5 word title without quotes."},
                        {"role": "user", "content": f"Title for: {user_text[:200]}"}
                    ],
                    max_tokens=15
                )
                smart_title = title_response.choices[0].message.content.strip().replace('"', '')
                
                conversation.title = smart_title
                conversation.save(update_fields=['title', 'updated_at'])
                
                async_to_sync(channel_layer.group_send)(
                    group_name,
                    {"type": "chat_title_update", "title": smart_title, "conversation_id": conversation_id}
                )
            except Exception as e:
                logger.error(f"Failed to generate title for conversation {conversation_id}: {e}")
        
        encoding = encoding_for_model("gpt-4o")
        system_prompt = "You are Rai, a helpful AI assistant."
        
        chat_history = [{"role": "system", "content": system_prompt}]
        token_count = len(encoding.encode(system_prompt))
        
        current_msg_tokens = len(encoding.encode(user_text))
        token_count += current_msg_tokens
        
        recent_messages = Message.objects.filter(
            conversation_id=conversation_id
        ).exclude(
            text=user_text, sender='user'
        ).order_by('-created_at')
        
        messages_to_include = []
        for msg in recent_messages:
            role = "assistant" if msg.sender == 'ai' else "user"
            msg_tokens = len(encoding.encode(msg.text))
            
            if token_count + msg_tokens > MAX_CONTEXT_TOKENS:
                break
            
            messages_to_include.insert(0, {"role": role, "content": msg.text})
            token_count += msg_tokens
        
        chat_history.extend(messages_to_include)
        chat_history.append({"role": "user", "content": user_text})
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=chat_history,
            max_tokens=2000,
            temperature=0.7
        )
        ai_text = response.choices[0].message.content
        
        Message.objects.create(conversation=conversation, sender='ai', text=ai_text)
        conversation.save(update_fields=['updated_at'])
        
        async_to_sync(channel_layer.group_send)(
            group_name,
            {"type": "chat_message", "message": ai_text, "sender": "ai"}
        )
        
        logger.info(f"Generated AI response for conversation {conversation_id}, tokens used: {token_count}")
        
    except Exception as e:
        logger.error(f"Error generating AI response for conversation {conversation_id}: {e}", exc_info=True)
        
        try:
            self.retry(exc=e)
        except self.MaxRetriesExceededError:
            async_to_sync(channel_layer.group_send)(
                group_name,
                {"type": "chat_error", "message": "AI service temporarily unavailable. Please try again."}
            )