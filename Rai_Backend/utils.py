from django.conf import settings
from django.core.mail import send_mail
from rest_framework.response import Response
from rest_framework import status

def get_client_ip(request):
    if not request:
        return None
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def send_email(subject, message, recipient_list, html_message=None):
    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            recipient_list,
            fail_silently=False,
            html_message=html_message
        )
        return True
    except Exception as e:
        print(f"Email Error: {e}")
        return False

def api_response(message, data=None, success=True, status_code=status.HTTP_200_OK, request=None, extra=None):
    payload = {
        "success": success,
        "message": message,
        "data": data if data is not None else {}
    }
    return Response(payload, status=status_code)