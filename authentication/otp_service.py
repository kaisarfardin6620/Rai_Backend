import secrets
import requests
from django.conf import settings
from Rai_Backend.utils import send_email
import logging

logger = logging.getLogger("authentication")

def generate_otp():
    return ''.join([str(secrets.randbelow(10)) for _ in range(6)])

def send_otp_sms(phone, otp, retries=3):
    if not settings.INFOBIP_BASE_URL or not settings.INFOBIP_API_KEY or not settings.INFOBIP_SENDER_ID:
        logger.error("Infobip SMS credentials not configured")
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
                "text": f"Your verification code is {otp}. It will expire in 3 minutes."
            }
        ]
    }

    for attempt in range(retries):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            response.raise_for_status()
            response_data = response.json()
            
            if response_data.get('messages') and response_data['messages'][0].get('status', {}).get('groupId') == 1:
                logger.info(f"SMS OTP sent successfully to {phone}")
                return True
            else:
                logger.warning(f"SMS OTP failed for {phone}: {response_data}")
                
        except requests.Timeout:
            logger.error(f"SMS OTP timeout (attempt {attempt + 1}/{retries}) for {phone}")
        except requests.RequestException as e:
            logger.error(f"SMS OTP failed (attempt {attempt + 1}/{retries}) for {phone}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    logger.error(f"Response: {e.response.text}")
                except Exception:
                    pass
        
        if attempt < retries - 1:
            continue
    
    return False

def send_otp_email(email, otp, subject=None):
    if not subject:
        subject = "Your Verification Code"

    message_text = f"Your verification code is {otp}. It will expire in 3 minutes. If you didn't request this code, please ignore this email."

    result = send_email(
        subject=subject,
        message=message_text,
        recipient_list=[email],
        retries=3
    )
    
    if result:
        logger.info(f"Email OTP sent successfully to {email}")
    else:
        logger.error(f"Email OTP failed for {email}")
    
    return result

def send_otp(destination, otp, method="sms"):
    if method == "sms":
        return send_otp_sms(destination, otp)
    elif method == "email":
        return send_otp_email(destination, otp)
    else:
        logger.error(f"Invalid OTP method: {method}")
        raise ValueError("Invalid OTP method. Must be 'sms' or 'email'.")