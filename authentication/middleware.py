from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import UntypedToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from jwt import decode as jwt_decode
from django.conf import settings
from django.contrib.auth import get_user_model
from urllib.parse import parse_qs
import logging
from django.core.cache import cache

logger = logging.getLogger("authentication")

@database_sync_to_async
def get_user(token_key):
    try:
        cache_key = f"ws_auth_{token_key[:20]}"
        cached_user_id = cache.get(cache_key)
        
        if cached_user_id:
            try:
                user = get_user_model().objects.get(id=cached_user_id, is_active=True)
                return user
            except get_user_model().DoesNotExist:
                cache.delete(cache_key)
        
        UntypedToken(token_key)
        decoded_data = jwt_decode(
            token_key, 
            settings.SECRET_KEY, 
            algorithms=["HS256"],
            options={"verify_exp": True}
        )
        
        user_id = decoded_data.get('user_id')
        if not user_id:
            logger.warning("No user_id in WebSocket token")
            return AnonymousUser()
        
        user = get_user_model().objects.get(id=user_id, is_active=True)
        cache.set(cache_key, user_id, 300)
        logger.info(f"WebSocket auth successful for user: {user.username}")
        return user
        
    except (InvalidToken, TokenError) as e:
        logger.warning(f"Invalid WebSocket token: {e}")
        return AnonymousUser()
    except get_user_model().DoesNotExist:
        logger.warning(f"User not found for WebSocket token")
        return AnonymousUser()
    except Exception as e:
        logger.error(f"WebSocket authentication error: {e}", exc_info=True)
        return AnonymousUser()

class JWTAuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        try:
            query_string = parse_qs(scope.get("query_string", b"").decode("utf8"))
            token = query_string.get("token")
            
            if token and len(token) > 0:
                logger.debug(f"WebSocket token received: {token[0][:20]}...")
                scope["user"] = await get_user(token[0])
            else:
                logger.warning("No token in WebSocket query string")
                scope["user"] = AnonymousUser()
        except Exception as e:
            logger.error(f"Middleware error: {e}", exc_info=True)
            scope["user"] = AnonymousUser()
        
        return await self.app(scope, receive, send)