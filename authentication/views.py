import structlog
from rest_framework.decorators import api_view, permission_classes, throttle_classes, parser_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView
from drf_spectacular.utils import extend_schema

from .serializers import (
    SignupInitiateSerializer, SignupVerifySerializer, SignupFinalizeSerializer, 
    ProfileSerializer, PasswordResetRequestSerializer, PasswordResetConfirmSerializer,
    PasswordChangeSerializer, LogoutSerializer, DeleteAccountSerializer,
    MyTokenObtainPairSerializer, ResendOTPSerializer,
    EmailChangeInitiateSerializer, EmailChangeVerifySerializer
)
from .services import AuthService

logger = structlog.get_logger(__name__)

                     

@extend_schema(
    request=SignupInitiateSerializer,
    responses={200: dict, 400: dict},
    summary="Initiate Signup (Send OTP)"
)
@api_view(['POST'])
@throttle_classes([ScopedRateThrottle])
def signup_initiate(request):
    """Step 1: Send OTP to Email or Phone."""
    serializer = SignupInitiateSerializer(data=request.data)
    if serializer.is_valid():
        identifier = serializer.validated_data['identifier']
        success, message, code = AuthService.initiate_otp(identifier, request)
        if success:
            return Response({"identifier": identifier, "message": message}, status=code)
        return Response({"message": message}, status=code)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
signup_initiate.throttle_scope = 'otp'

@extend_schema(
    request=SignupVerifySerializer,
    responses={200: dict, 400: dict},
    summary="Verify Signup OTP"
)
@api_view(['POST'])
@throttle_classes([ScopedRateThrottle])
def signup_verify(request):
    """Step 2: Verify the OTP."""
    serializer = SignupVerifySerializer(data=request.data)
    if serializer.is_valid():
        success, message, code = AuthService.verify_otp(
            serializer.validated_data['identifier'],
            serializer.validated_data['otp'],
            request
        )
        if success:
            return Response({"message": message}, status=code)
        return Response({"message": message}, status=code)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
signup_verify.throttle_scope = 'anon'

@extend_schema(
    request=SignupFinalizeSerializer,
    responses={201: dict, 400: dict},
    summary="Finalize Signup (Create User)"
)
@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@throttle_classes([ScopedRateThrottle])
def signup_finalize(request):
    """Step 3: Create User Profile (requires verified OTP)."""
    serializer = SignupFinalizeSerializer(data=request.data)
    if serializer.is_valid():
        identifier = serializer.validated_data['identifier']
        success, message, code = AuthService.register_user({'identifier': identifier})
        if success is None:
             return Response({"message": message}, status=code)

        user = serializer.save()
        tokens = AuthService.login_user(user)
        user_data = ProfileSerializer(user, context={'request': request}).data
        
        response_data = tokens
        response_data['user'] = user_data
        response_data['message'] = "Account created successfully."

        logger.info("user_registered", user_id=user.id)
        return Response(response_data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
signup_finalize.throttle_scope = 'anon'

               

class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

    @extend_schema(summary="Login (Get Tokens)")
    def post(self, request, *args, **kwargs):
        try:
            response = super().post(request, *args, **kwargs)
            response.data['message'] = "Login successful"
            logger.info("user_logged_in", username=request.data.get('username'))
            return response
        except Exception as e:
            raise e

                            

@extend_schema(responses={200: ProfileSerializer}, summary="Get Profile")
@api_view(['GET'])
@permission_classes([IsAuthenticated])
@throttle_classes([ScopedRateThrottle])
def get_profile(request):
    serializer = ProfileSerializer(request.user, context={'request': request})
    return Response(serializer.data)
get_profile.throttle_scope = 'user'

@extend_schema(request=ProfileSerializer, responses={200: ProfileSerializer}, summary="Update Profile")
@api_view(['PUT'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@throttle_classes([ScopedRateThrottle])
def update_profile(request):
    serializer = ProfileSerializer(request.user, data=request.data, partial=True, context={'request': request})
    if serializer.is_valid():
        serializer.save()
        return Response({"message": "Profile updated", "data": serializer.data})
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
update_profile.throttle_scope = 'user'

                             

@extend_schema(request=PasswordResetRequestSerializer, responses={200: dict}, summary="Request Password Reset")
@api_view(['POST'])
@throttle_classes([ScopedRateThrottle])
def password_reset_request(request):
    serializer = PasswordResetRequestSerializer(data=request.data)
    if serializer.is_valid():
        identifier = serializer.validated_data['identifier']
        success, message, code = AuthService.initiate_otp(identifier, request)
        if success:
             return Response({"message": "If account exists, OTP sent."}, status=200)
        return Response({"message": message}, status=code)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
password_reset_request.throttle_scope = 'otp'

@extend_schema(request=PasswordResetConfirmSerializer, responses={200: dict}, summary="Confirm Password Reset")
@api_view(['POST'])
@throttle_classes([ScopedRateThrottle])
def password_reset_confirm(request):
    serializer = PasswordResetConfirmSerializer(data=request.data, context={'request': request})
    if serializer.is_valid():
        serializer.save()
        return Response({"message": "Password reset successfully."})
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
password_reset_confirm.throttle_scope = 'anon'

@extend_schema(request=PasswordChangeSerializer, responses={200: dict}, summary="Change Password")
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([ScopedRateThrottle])
def change_password(request):
    serializer = PasswordChangeSerializer(data=request.data, context={'request': request})
    if serializer.is_valid():
        serializer.save()
        return Response({"message": "Password changed successfully."})
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
change_password.throttle_scope = 'user'

                         

@extend_schema(request=LogoutSerializer, responses={200: dict}, summary="Logout")
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([ScopedRateThrottle])
def logout_view(request):
    serializer = LogoutSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response({"message": "Logged out successfully."})
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
logout_view.throttle_scope = 'user'

@extend_schema(request=DeleteAccountSerializer, responses={200: dict}, summary="Delete Account")
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
@throttle_classes([ScopedRateThrottle])
def delete_account(request):
    serializer = DeleteAccountSerializer(data=request.data, context={'request': request})
    if serializer.is_valid():
        serializer.save()
        return Response({"message": "Account deactivated."})
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
delete_account.throttle_scope = 'user'

@extend_schema(request=ResendOTPSerializer, responses={200: dict}, summary="Resend OTP")
@api_view(['POST'])
@throttle_classes([ScopedRateThrottle])
def resend_otp(request):
    serializer = ResendOTPSerializer(data=request.data)
    if serializer.is_valid():
        identifier = serializer.validated_data['identifier']
        success, message, code = AuthService.initiate_otp(identifier, request)
        if success:
            return Response({"message": "OTP resent successfully."})
        return Response({"message": message}, status=code)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
resend_otp.throttle_scope = 'otp'

                      

@extend_schema(request=EmailChangeInitiateSerializer, responses={200: dict}, summary="Initiate Email Change")
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([ScopedRateThrottle])
def initiate_email_change(request):
    serializer = EmailChangeInitiateSerializer(data=request.data, context={'request': request})
    if serializer.is_valid():
        new_email = serializer.validated_data['new_email']
        success, message, code = AuthService.initiate_otp(new_email, request)
        if success:
            from django.core.cache import cache
            cache.set(f"pending_email_change_{request.user.id}", new_email, 600)
            return Response({"message": f"OTP sent to {new_email}"})
        return Response({"message": message}, status=code)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
initiate_email_change.throttle_scope = 'otp'

@extend_schema(request=EmailChangeVerifySerializer, responses={200: dict}, summary="Verify Email Change")
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([ScopedRateThrottle])
def verify_email_change(request):
    serializer = EmailChangeVerifySerializer(data=request.data)
    if serializer.is_valid():
        from django.core.cache import cache
        new_email = cache.get(f"pending_email_change_{request.user.id}")
        if not new_email:
            return Response({"message": "Request expired."}, status=400)

        success, message, code = AuthService.verify_otp(new_email, serializer.validated_data['otp'], request)
        if success:
            user = request.user
            user.email = new_email
            user.save(update_fields=['email'])
            cache.delete(f"pending_email_change_{request.user.id}")
            return Response({"message": "Email updated successfully.", "email": new_email})
        return Response({"message": message}, status=code)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
verify_email_change.throttle_scope = 'otp'

@extend_schema(request=None, responses={200: dict}, summary="Resend Email Change OTP")
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([ScopedRateThrottle])
def resend_email_change_otp(request):
    from django.core.cache import cache
    new_email = cache.get(f"pending_email_change_{request.user.id}")
    if not new_email:
        return Response({"message": "No pending request found."}, status=400)
        
    success, message, code = AuthService.initiate_otp(new_email, request)
    if success:
        return Response({"message": "OTP resent."})
    return Response({"message": message}, status=code)
resend_email_change_otp.throttle_scope = 'otp'