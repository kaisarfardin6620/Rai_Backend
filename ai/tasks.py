from celery import shared_task
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.conf import settings
from openai import OpenAI
from .models import Conversation, Message

@shared_task
def generate_ai_response(conversation_id, user_text, user_id, is_new_chat=False):
    channel_layer = get_channel_layer()
    group_name = f"chat_{conversation_id}"
    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    try:
        recent_messages = Message.objects.filter(conversation_id=conversation_id).order_by('-created_at')[:15]
        recent_messages = reversed(recent_messages)
        
        chat_history = [{"role": "system", "content": "You are Rai, a helpful AI assistant."}]
        for msg in recent_messages:
            role = "assistant" if msg.sender == 'ai' else "user"
            chat_history.append({"role": role, "content": msg.text})

        if not chat_history or chat_history[-1]['content'] != user_text:
             chat_history.append({"role": "user", "content": user_text})

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=chat_history
        )
        ai_text = response.choices[0].message.content

        conversation = Conversation.objects.get(id=conversation_id)
        Message.objects.create(conversation=conversation, sender='ai', text=ai_text)
        
        conversation.save() 

        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": "chat_message",
                "message": ai_text,
                "sender": "ai"
            }
        )

        if is_new_chat:
            try:
                title_response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant."},
                        {"role": "user", "content": f"Summarize this message into a short, concise, 3-5 word title. Do not use quotes. Message: {user_text}"}
                    ],
                    max_tokens=15
                )
                smart_title = title_response.choices[0].message.content.strip().replace('"', '')

                conversation.title = smart_title
                conversation.save()

                async_to_sync(channel_layer.group_send)(
                    group_name,
                    {
                        "type": "chat_title_update",
                        "title": smart_title,
                        "conversation_id": conversation_id
                    }
                )
            except Exception as e:
                print(f"Failed to generate title: {e}")

    except Exception as e:
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": "chat_error",
                "message": f"AI Error: {str(e)}"
            }
        )