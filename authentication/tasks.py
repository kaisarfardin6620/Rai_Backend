import logging
from celery import shared_task
from django.core.management import call_command

logger = logging.getLogger(__name__)

@shared_task(bind=True)
def flush_expired_tokens_task(self):
    """
    Periodic task to clear out expired outstanding and blacklisted tokens
    from the rest_framework_simplejwt.token_blacklist tables.
    """
    try:
        call_command("flushexpiredtokens")
        logger.info("Successfully flushed expired SimpleJWT tokens.")
        return "Tokens Flushed"
    except Exception as e:
        logger.error(f"Error flushing expired tokens: {e}")
        return str(e)
