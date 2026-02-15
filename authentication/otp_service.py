import structlog
import requests
from django.conf import settings
from Rai_Backend.utils import send_email, get_client_ip
import secrets

logger = structlog.get_logger(__name__)

def generate_otp():
    return ''.join(secrets.choice('0123456789') for _ in range(6))

def send_otp_sms(phone, otp):
    if not settings.INFOBIP_BASE_URL:
        logger.error("infobip_config_missing")
        return False
    
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
                "text": f"Your verification code is {otp}. Expires in 3 minutes."
            }
        ]
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        logger.info("sms_sent", phone=phone)
        return True
    except Exception as e:
        logger.error("sms_failed", error=str(e), phone=phone)
        return False

def send_otp_email(email, otp):
    subject = "Your Verification Code"
    message = f"Your verification code is {otp}. Expires in 3 minutes."
    
    return send_email(subject, message, [email])

def send_otp(identifier, otp, method="email"):
    if method == "email":
        return send_otp_email(identifier, otp)
    elif method == "sms":
        return send_otp_sms(identifier, otp)
    return False