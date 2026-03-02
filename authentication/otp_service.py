import structlog
import requests
import secrets
from django.conf import settings

logger = structlog.get_logger(__name__)

def generate_otp():
    return ''.join(secrets.choice('0123456789') for _ in range(6))

def send_otp_sms(phone, otp):
    url = f"{settings.INFOBIP_BASE_URL}/sms/3/messages"
    headers = {
        "Authorization": f"App {settings.INFOBIP_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    phone = phone.replace("+", "")
    
    payload = {
        "messages": [
            {
                "destinations": [{"to": phone}],
                "sender": settings.INFOBIP_SENDER_ID,
                "content": {
                    "text": f"Your verification code is {otp}. Expires in 3 minutes."
                }
            }
        ]
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        logger.info("sms_sent", phone=phone)
        return True
    except requests.exceptions.RequestException as e:
        err_msg = e.response.text if e.response is not None else str(e)
        logger.error("sms_failed", error=str(e), phone=phone, response=err_msg)
        return False

def send_otp_email(email, otp):
    url = f"{settings.INFOBIP_BASE_URL}/email/4/messages"
    headers = {
        "Authorization": f"App {settings.INFOBIP_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    payload = {
        "messages":[
            {
                "destinations": [{"to": [{"destination": email}]}],
                "sender": settings.DEFAULT_FROM_EMAIL,
                "content": {
                    "subject": "Your Verification Code",
                    "text": f"Your verification code is {otp}. Expires in 3 minutes."
                }
            }
        ]
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        logger.info("email_sent", email=email)
        return True
    except requests.exceptions.RequestException as e:
        err_msg = e.response.text if e.response is not None else str(e)
        logger.error("email_failed", error=str(e), email=email, response=err_msg)
        return False

def send_otp(identifier, otp, method="email"):
    if method == "email":
        return send_otp_email(identifier, otp)
    elif method == "sms":
        return send_otp_sms(identifier, otp)
    return False