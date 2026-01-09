from rest_framework.decorators import api_view, permission_classes, parser_classes, throttle_classes
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
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
    MyTokenObtainPairSerializer
)
from .otp_service import generate_otp, send_otp
from .models import User, OTP
from Rai_Backend.utils import api_response, get_client_ip

logger = logging.getLogger("authentication")

class OTPThrottle(AnonRateThrottle):
    rate = '3/hour'

class LoginThrottle(AnonRateThrottle):
    rate = '10/hour'

@api_view(['POST'])
@throttle_classes([OTPThrottle])
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

@api_view(['POST'])
@throttle_classes([AnonRateThrottle])
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

@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@throttle_classes([AnonRateThrottle])
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

class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer
    throttle_classes = [LoginThrottle]

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
@throttle_classes([OTPThrottle])
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

@api_view(['POST'])
@throttle_classes([AnonRateThrottle])
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
        
        dest = user.email if user.email else user.phone
        otp_record = OTP.objects.filter(identifier=dest).order_by('-created_at').first()
        
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

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@throttle_classes([UserRateThrottle])
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

@api_view(['PUT'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@throttle_classes([UserRateThrottle])
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

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([UserRateThrottle])
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

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([UserRateThrottle])
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

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
@throttle_classes([UserRateThrottle])
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