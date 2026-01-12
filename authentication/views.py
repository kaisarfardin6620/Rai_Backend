from rest_framework.decorators import api_view, permission_classes, parser_classes, throttle_classes
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from django.core.cache import cache
from django.db import transaction
import logging
from django.utils.crypto import constant_time_compare
from .serializers import (
    SignupInitiateSerializer, SignupVerifySerializer, SignupFinalizeSerializer, ProfileSerializer,
    PasswordResetRequestSerializer, PasswordResetConfirmSerializer,
    PasswordChangeSerializer, LogoutSerializer, DeleteAccountSerializer,
    MyTokenObtainPairSerializer,ResendOTPSerializer,EmailChangeInitiateSerializer, EmailChangeVerifySerializer
)
from .otp_service import generate_otp, send_otp
from .models import User, OTP
from Rai_Backend.utils import api_response, get_client_ip

logger = logging.getLogger("authentication")

@api_view(['POST'])
@throttle_classes([ScopedRateThrottle])
def signup_initiate(request):
    try:
        serializer = SignupInitiateSerializer(data=request.data)
        if not serializer.is_valid():
            return api_response(
                message="Validation failed",
                data=serializer.errors,
                success=False,
                status_code=status.HTTP_400_BAD_REQUEST,
                request=request
            )

        destination = serializer.validated_data['identifier']
        method = "email" if "@" in destination else "sms"
        rate_limit_key = f"otp_limit_{destination}"
        if cache.get(rate_limit_key):
            return api_response(
                message="Please wait before requesting another OTP.",
                success=False,
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                request=request
            )
        
        with transaction.atomic():
            OTP.objects.filter(identifier=destination).delete()
            otp_code = generate_otp()
            OTP.objects.create(identifier=destination, code=otp_code, is_verified=False)
        
        send_result = send_otp(destination, otp_code, method=method)
        
        if send_result:
            cache.set(rate_limit_key, True, 60)
            
            return api_response(
                message="OTP sent successfully.",
                data={"identifier": destination},
                status_code=status.HTTP_200_OK,
                request=request
            )
        else:
            return api_response(
                message="Failed to send OTP. Please try again.",
                success=False,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                request=request
            )
    
    except Exception as e:
        logger.error(f"Error in signup_initiate: {e}", exc_info=True)
        return api_response(
            message="An error occurred. Please try again.",
            success=False,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            request=request
        )
signup_initiate.throttle_scope = 'otp'

@api_view(['POST'])
@throttle_classes([ScopedRateThrottle])
def signup_verify(request):
    try:
        serializer = SignupVerifySerializer(data=request.data)
        if not serializer.is_valid():
            return api_response(
                message="Validation failed",
                data=serializer.errors,
                success=False,
                status_code=status.HTTP_400_BAD_REQUEST,
                request=request
            )

        identifier = serializer.validated_data['identifier']
        otp_input = serializer.validated_data['otp']

        client_ip = get_client_ip(request)
        ip_rate_limit_key = f"otp_verify_{identifier}_{client_ip}"
        ip_attempts = cache.get(ip_rate_limit_key, 0)
        
        if ip_attempts >= 5:
            return api_response(
                message="Too many attempts from your IP. Please try again later.",
                success=False,
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                request=request
            )
        
        cache.set(ip_rate_limit_key, ip_attempts + 1, 300)

        otp_record = OTP.objects.filter(identifier=identifier).order_by('-created_at').first()
        
        if not otp_record:
            return api_response(
                message="No OTP found. Please request a new one.",
                success=False,
                status_code=status.HTTP_400_BAD_REQUEST,
                request=request
            )
        
        if not otp_record.is_valid():
            return api_response(
                message="OTP has expired or maximum attempts reached.",
                success=False,
                status_code=status.HTTP_400_BAD_REQUEST,
                request=request
            )
        
        if not constant_time_compare(otp_record.code, otp_input):
            otp_record.increment_attempts()
            remaining = 5 - otp_record.attempts
            return api_response(
                message=f"Invalid OTP. {remaining} attempts remaining.",
                success=False,
                status_code=status.HTTP_400_BAD_REQUEST,
                request=request
            )
        
        otp_record.is_verified = True
        otp_record.save(update_fields=['is_verified'])
        
        return api_response(
            message="OTP verified successfully.",
            data={"identifier": identifier},
            status_code=status.HTTP_200_OK,
            request=request
        )
    
    except Exception as e:
        logger.error(f"Error in signup_verify: {e}", exc_info=True)
        return api_response(
            message="An error occurred. Please try again.",
            success=False,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            request=request
        )
signup_verify.throttle_scope = 'anon'

@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@throttle_classes([ScopedRateThrottle])
def signup_finalize(request):
    try:
        serializer = SignupFinalizeSerializer(data=request.data)
        
        if not serializer.is_valid():
            return api_response(
                message="Validation failed",
                data=serializer.errors,
                success=False,
                status_code=status.HTTP_400_BAD_REQUEST,
                request=request
            )

        identifier = serializer.validated_data['identifier']
        otp_record = OTP.objects.filter(identifier=identifier, is_verified=True).order_by('-created_at').first()
        
        if not otp_record:
            return api_response(
                message="OTP not verified. Please verify OTP first.",
                success=False,
                status_code=status.HTTP_403_FORBIDDEN,
                request=request
            )
        
        with transaction.atomic():
            user = serializer.save()
            OTP.objects.filter(identifier=identifier).delete()
        
        refresh = RefreshToken.for_user(user)
        user_data = ProfileSerializer(user, context={'request': request}).data

        logger.info(f"New user registered: {user.username} from IP {get_client_ip(request)}")

        return api_response(
            message="Account created successfully.",
            data={
                "user": user_data,
                "access": str(refresh.access_token),
                "refresh": str(refresh)
            },
            status_code=status.HTTP_201_CREATED,
            request=request
        )
    
    except Exception as e:
        logger.error(f"Error in signup_finalize: {e}", exc_info=True)
        return api_response(
            message="An error occurred. Please try again.",
            success=False,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            request=request
        )
signup_finalize.throttle_scope = 'anon'

class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

    def post(self, request, *args, **kwargs):
        try:
            response = super().post(request, *args, **kwargs)
            if response.status_code == 200:
                username = request.data.get('username', '').lower().strip()
                logger.info(f"User logged in: {username} from IP {get_client_ip(request)}")
                
                return api_response(
                    message="Login successful.",
                    data=response.data,
                    status_code=status.HTTP_200_OK,
                    request=request
                )
            return api_response(
                message="Invalid credentials.",
                data=response.data,
                success=False,
                status_code=response.status_code,
                request=request
            )
        except Exception as e:
            logger.warning(f"Failed login attempt from IP {get_client_ip(request)}: {e}")
            return api_response(
                message="Invalid credentials.",
                success=False,
                status_code=status.HTTP_401_UNAUTHORIZED,
                request=request
            )

@api_view(['POST'])
@throttle_classes([ScopedRateThrottle])
def password_reset_request(request):
    try:
        serializer = PasswordResetRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return api_response(
                message="Validation failed",
                data=serializer.errors,
                success=False,
                status_code=status.HTTP_400_BAD_REQUEST,
                request=request
            )

        identifier = serializer.validated_data['identifier']
        
        rate_limit_key = f"pwd_reset_{identifier}"
        if cache.get(rate_limit_key):
            return api_response(
                message="Please wait before requesting another OTP.",
                success=False,
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                request=request
            )
        
        if '@' in identifier:
            user = User.objects.filter(email=identifier).first()
            method = "email"
        else:
            user = User.objects.filter(phone=identifier).first()
            method = "sms"

        if user:
            with transaction.atomic():
                OTP.objects.filter(identifier=identifier).delete()
                otp_code = generate_otp()
                OTP.objects.create(identifier=identifier, code=otp_code)
            
            send_result = send_otp(identifier, otp_code, method=method)
            
            if send_result:
                cache.set(rate_limit_key, True, 60)
        
        return api_response(
            message=f"If the account exists, an OTP has been sent.",
            status_code=status.HTTP_200_OK,
            request=request
        )
    
    except Exception as e:
        logger.error(f"Error in password_reset_request: {e}", exc_info=True)
        return api_response(
            message="An error occurred. Please try again.",
            success=False,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            request=request
        )
password_reset_request.throttle_scope = 'otp'

@api_view(['POST'])
@throttle_classes([ScopedRateThrottle])
def password_reset_confirm(request):
    try:
        serializer = PasswordResetConfirmSerializer(data=request.data, context={'request': request})
        
        username = request.data.get('username', '').lower().strip()
        otp_code = request.data.get('otp')
        
        user = User.objects.filter(username=username).first()
        
        if not user:
            return api_response(
                message="Invalid request.",
                success=False,
                status_code=status.HTTP_400_BAD_REQUEST,
                request=request
            )
        
        identifiers = []
        if user.email:
            identifiers.append(user.email)
        if user.phone:
            identifiers.append(user.phone)
        otp_record = OTP.objects.filter(identifier__in=identifiers).order_by('-created_at').first()
        if otp_record:
            dest = otp_record.identifier
        else:
            dest = None
        
        if not otp_record or not otp_record.is_valid():
            return api_response(
                message="Invalid or expired OTP.",
                success=False,
                status_code=status.HTTP_400_BAD_REQUEST,
                request=request
            )
        
        if not constant_time_compare(otp_record.code, otp_code):
            otp_record.increment_attempts()
            return api_response(
                message="Invalid OTP.",
                success=False,
                status_code=status.HTTP_400_BAD_REQUEST,
                request=request
            )
        
        if serializer.is_valid():
            with transaction.atomic():
                serializer.save()
                OTP.objects.filter(identifier=dest).delete()

            logger.info(f"Password reset successful for user: {username}")

            return api_response(
                message="Password reset successfully.",
                status_code=status.HTTP_200_OK,
                request=request
            )
        
        return api_response(
            message="Validation failed",
            data=serializer.errors,
            success=False,
            status_code=status.HTTP_400_BAD_REQUEST,
            request=request
        )
    
    except Exception as e:
        logger.error(f"Error in password_reset_confirm: {e}", exc_info=True)
        return api_response(
            message="An error occurred. Please try again.",
            success=False,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            request=request
        )
password_reset_confirm.throttle_scope = 'anon'

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@throttle_classes([ScopedRateThrottle])
def get_profile(request):
    try:
        serializer = ProfileSerializer(request.user, context={'request': request})
        return api_response(
            message="Profile fetched successfully.",
            data=serializer.data,
            status_code=status.HTTP_200_OK,
            request=request
        )
    except Exception as e:
        logger.error(f"Error in get_profile: {e}", exc_info=True)
        return api_response(
            message="An error occurred.",
            success=False,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            request=request
        )
get_profile.throttle_scope = 'user'

@api_view(['PUT'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@throttle_classes([ScopedRateThrottle])
def update_profile(request):
    try:
        serializer = ProfileSerializer(request.user, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            
            logger.info(f"Profile updated for user: {request.user.username}")
            
            return api_response(
                message="Profile updated successfully.",
                data=serializer.data,
                status_code=status.HTTP_200_OK,
                request=request
            )
        return api_response(
            message="Validation failed",
            data=serializer.errors,
            success=False,
            status_code=status.HTTP_400_BAD_REQUEST,
            request=request
        )
    except Exception as e:
        logger.error(f"Error in update_profile: {e}", exc_info=True)
        return api_response(
            message="An error occurred.",
            success=False,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            request=request
        )
update_profile.throttle_scope = 'user'

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([ScopedRateThrottle])
def change_password(request):
    try:
        serializer = PasswordChangeSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            
            logger.info(f"Password changed for user: {request.user.username}")
            
            return api_response(
                message="Password changed successfully.",
                status_code=status.HTTP_200_OK,
                request=request
            )
        return api_response(
            message="Validation failed",
            data=serializer.errors,
            success=False,
            status_code=status.HTTP_400_BAD_REQUEST,
            request=request
        )
    except Exception as e:
        logger.error(f"Error in change_password: {e}", exc_info=True)
        return api_response(
            message="An error occurred.",
            success=False,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            request=request
        )
change_password.throttle_scope = 'user'

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([ScopedRateThrottle])
def logout_view(request):
    try:
        serializer = LogoutSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            
            logger.info(f"User logged out: {request.user.username}")
            
            return api_response(
                message="Logged out successfully.",
                status_code=status.HTTP_200_OK,
                request=request
            )
        return api_response(
            message="Validation failed",
            data=serializer.errors,
            success=False,
            status_code=status.HTTP_400_BAD_REQUEST,
            request=request
        )
    except Exception as e:
        logger.error(f"Error in logout: {e}", exc_info=True)
        return api_response(
            message="An error occurred.",
            success=False,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            request=request
        )
logout_view.throttle_scope = 'user'

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
@throttle_classes([ScopedRateThrottle])
def delete_account(request):
    try:
        serializer = DeleteAccountSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            username = request.user.username
            serializer.save()
            
            logger.warning(f"Account deactivated for user: {username}")
            
            return api_response(
                message="Account deactivated successfully.",
                status_code=status.HTTP_200_OK,
                request=request
            )
        return api_response(
            message="Validation failed",
            data=serializer.errors,
            success=False,
            status_code=status.HTTP_400_BAD_REQUEST,
            request=request
        )
    except Exception as e:
        logger.error(f"Error in delete_account: {e}", exc_info=True)
        return api_response(
            message="An error occurred.",
            success=False,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            request=request
        )
delete_account.throttle_scope = 'user'

@api_view(['POST'])
@throttle_classes([ScopedRateThrottle])
def resend_otp(request):
    try:
        serializer = ResendOTPSerializer(data=request.data)
        if not serializer.is_valid():
            return api_response(
                message="Validation failed",
                data=serializer.errors,
                success=False,
                status_code=status.HTTP_400_BAD_REQUEST,
                request=request
            )

        identifier = serializer.validated_data['identifier']
        cooldown_key = f"resend_cooldown_{identifier}"
        if cache.get(cooldown_key):
            return api_response(
                message="Please wait 60 seconds before requesting a new code.",
                success=False,
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                request=request
            )

        with transaction.atomic():
            OTP.objects.filter(identifier=identifier).delete()
            otp_code = generate_otp()
            OTP.objects.create(identifier=identifier, code=otp_code)

        method = "email" if "@" in identifier else "sms"
        send_result = send_otp(identifier, otp_code, method=method)

        if send_result:
            cache.set(cooldown_key, True, 60)
            
            return api_response(
                message="OTP resent successfully.",
                status_code=status.HTTP_200_OK,
                request=request
            )
        else:
            return api_response(
                message="Failed to send OTP. Please try again later.",
                success=False,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                request=request
            )

    except Exception as e:
        logger.error(f"Error in resend_otp: {e}", exc_info=True)
        return api_response(
            message="An error occurred.",
            success=False,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            request=request
        )
resend_otp.throttle_scope = 'otp'

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([ScopedRateThrottle])
def initiate_email_change(request):
    """
    Step 1: Validate new email, generate OTP, send to NEW email, cache the request.
    """
    try:
        serializer = EmailChangeInitiateSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return api_response(message="Validation failed", data=serializer.errors, success=False, status_code=400, request=request)

        new_email = serializer.validated_data['new_email']
        
        # Rate limit check specifically for email change
        rate_limit_key = f"email_change_limit_{request.user.id}"
        if cache.get(rate_limit_key):
             return api_response(message="Please wait before requesting another code.", success=False, status_code=429, request=request)

        # Generate OTP
        otp_code = generate_otp()
        
        # Store in Redis: Key includes UserID, Value is {email, code}
        # Expires in 10 minutes (600 seconds)
        cache_key = f"pending_email_change_{request.user.id}"
        cache.set(cache_key, {"email": new_email, "otp": otp_code}, 600)
        
        # Send OTP to the NEW email address
        send_result = send_otp(new_email, otp_code, method="email")
        
        if send_result:
            cache.set(rate_limit_key, True, 60) # 60 second cooldown
            return api_response(
                message=f"OTP sent to {new_email}. Please verify to complete the change.",
                status_code=200,
                request=request
            )
        else:
            return api_response(message="Failed to send OTP. Try again.", success=False, status_code=500, request=request)

    except Exception as e:
        logger.error(f"Error in initiate_email_change: {e}", exc_info=True)
        return api_response(message="An error occurred.", success=False, status_code=500, request=request)

initiate_email_change.throttle_scope = 'otp'

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([ScopedRateThrottle])
def verify_email_change(request):
    """
    Step 2: Check OTP. If valid, update the user's email in the DB.
    """
    try:
        serializer = EmailChangeVerifySerializer(data=request.data)
        if not serializer.is_valid():
            return api_response(message="Invalid OTP format", data=serializer.errors, success=False, status_code=400, request=request)

        user_otp = serializer.validated_data['otp']
        cache_key = f"pending_email_change_{request.user.id}"
        cached_data = cache.get(cache_key)

        if not cached_data:
            return api_response(message="OTP expired or request invalid. Please start over.", success=False, status_code=400, request=request)

        # Verify OTP (Using constant_time_compare for security)
        if not constant_time_compare(cached_data['otp'], user_otp):
            return api_response(message="Invalid OTP.", success=False, status_code=400, request=request)

        # OTP Matches! Perform the update
        with transaction.atomic():
            user = request.user
            new_email = cached_data['email']
            
            # Double check uniqueness just in case someone took it in the last 2 minutes
            if User.objects.filter(email=new_email).exclude(id=user.id).exists():
                 return api_response(message="This email is already taken.", success=False, status_code=400, request=request)

            user.email = new_email
            # Optional: Reset email verification status if you require verified emails
            # user.is_email_verified = True 
            user.save(update_fields=['email'])
            
            # Clear the cache
            cache.delete(cache_key)

        logger.info(f"User {user.id} changed email to {new_email}")
        
        return api_response(
            message="Email changed successfully.",
            data={"new_email": new_email},
            status_code=200,
            request=request
        )

    except Exception as e:
        logger.error(f"Error in verify_email_change: {e}", exc_info=True)
        return api_response(message="An error occurred.", success=False, status_code=500, request=request)
    
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([ScopedRateThrottle])
def resend_email_change_otp(request):
    try:
        rate_limit_key = f"email_change_resend_limit_{request.user.id}"
        if cache.get(rate_limit_key):
            return api_response(
                message="Please wait 60 seconds before requesting a new code.",
                success=False,
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                request=request
            )

        cache_key = f"pending_email_change_{request.user.id}"
        cached_data = cache.get(cache_key)
        
        if not cached_data:
            return api_response(
                message="No pending email change request found. Please initiate again.",
                success=False,
                status_code=status.HTTP_400_BAD_REQUEST,
                request=request
            )

        new_otp = generate_otp()
        
        cached_data['otp'] = new_otp
        cache.set(cache_key, cached_data, 600)
        
        target_email = cached_data['email']
        send_result = send_otp(target_email, new_otp, method="email")

        if send_result:
            cache.set(rate_limit_key, True, 60)
            return api_response(
                message=f"New OTP sent to {target_email}.",
                status_code=200,
                request=request
            )
        else:
            return api_response(message="Failed to send OTP.", success=False, status_code=500, request=request)

    except Exception as e:
        logger.error(f"Error in resend_email_change_otp: {e}", exc_info=True)
        return api_response(message="An error occurred.", success=False, status_code=500, request=request)

resend_email_change_otp.throttle_scope = 'otp'    