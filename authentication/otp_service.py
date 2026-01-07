import secrets
import requests
from django.conf import settings
from django.core.mail import send_mail
import logging

logger = logging.getLogger("myapp")

def generate_otp():
    return ''.join([str(secrets.randbelow(10)) for _ in range(6)])

def send_otp_sms(phone, otp):
    url = f"{settings.INFOBIP_BASE_URL}/sms/2/text/advanced"
    headers = {
        "Authorization": f"App {settings.INFOBIP_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    payload = {
        "messages": [
            {
                "from": settings.INFOBIP_SENDER_ID,
                "destinations": [{"to": phone}],
                "text": f"Your verification code is {otp}. It will expire in 5 minutes."
            }
        ]
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        response_data = response.json()
        logger.info(f"Infobip SMS Response for {phone}: {response_data}")
        return response_data
    except requests.RequestException as e:
        logger.error(f"SMS OTP sending failed: {e}")
        if e.response is not None:
            try:
                logger.error(f"Infobip Error Response: {e.response.text}")
            except Exception:
                pass
        return None

def send_otp_email(email, otp, subject=None):
    if not subject:
        subject = "Your Verification Code"

    message_text = f"Your verification code is {otp}. It will expire in 5 minutes."

    try:
        send_mail(
            subject,
            message_text,
            settings.DEFAULT_FROM_EMAIL,
            [email],
            fail_silently=False,
        )
        logger.info(f"OTP sent via Email to {email}")
        return True
    except Exception as e:
        logger.error(f"Email sending failed: {e}")
        if hasattr(e, 'response'): 
            logger.error(f"API Response: {e.response.content}")
        return False

def send_otp(destination, otp, method="sms"):
    if method == "sms":
        return send_otp_sms(destination, otp)
    elif method == "email":
        return send_otp_email(destination, otp)
    else:
        raise ValueError("Invalid OTP method. Must be 'sms' or 'email'.")