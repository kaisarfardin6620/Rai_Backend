from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
import logging

from .serializers import (
    SignupInitiateSerializer, SignupVerifySerializer, SignupFinalizeSerializer, ProfileSerializer,
    PasswordResetRequestSerializer, PasswordResetConfirmSerializer,
    PasswordChangeSerializer, LogoutSerializer, DeleteAccountSerializer,
    MyTokenObtainPairSerializer
)
from .otp_service import generate_otp, send_otp
from .models import User, OTP
from Rai_Backend.utils import api_response

logger = logging.getLogger("myapp")

@api_view(['POST'])
def signup_initiate(request):
    serializer = SignupInitiateSerializer(data=request.data)
    if not serializer.is_valid():
        return api_response(
            message="Validation failed",
            data=serializer.errors,
            success=False,
            status_code=status.HTTP_400_BAD_REQUEST,
            request=request
        )

    email = serializer.validated_data.get('email')
    phone = serializer.validated_data.get('phone')
    destination = email if email else phone
    method = "email" if email else "sms"
    otp_code = generate_otp()
    OTP.objects.filter(identifier=destination).delete()
    OTP.objects.create(identifier=destination, code=otp_code, is_verified=False)
    
    send_otp(destination, otp_code, method=method)

    return api_response(
        message="OTP sent successfully.",
        data={"identifier": destination},
        status_code=status.HTTP_200_OK,
        request=request
    )

@api_view(['POST'])
def signup_verify(request):
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

    try:
        otp_record = OTP.objects.filter(identifier=identifier, code=otp_input).last()
        if otp_record and otp_record.is_valid():
            otp_record.is_verified = True
            otp_record.save()
            return api_response(
                message="OTP Verified.",
                data={"identifier": identifier},
                status_code=status.HTTP_200_OK,
                request=request
            )
    except Exception:
        pass

    return api_response(
        message="Invalid or expired OTP.",
        success=False,
        status_code=status.HTTP_400_BAD_REQUEST,
        request=request
    )

@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def signup_finalize(request):
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
    otp_record = OTP.objects.filter(identifier=identifier).last()
    
    if otp_record and otp_record.is_verified:
        user = serializer.save()
        OTP.objects.filter(identifier=identifier).delete()
        refresh = RefreshToken.for_user(user)
        user_data = ProfileSerializer(user, context={'request': request}).data

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
    
    return api_response(
        message="Phone/Email not verified or session expired. Please request OTP again.",
        success=False,
        status_code=status.HTTP_403_FORBIDDEN,
        request=request
    )

class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
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

@api_view(['POST'])
def password_reset_request(request):
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
    
    if '@' in identifier:
        user = User.objects.filter(email=identifier).first()
        method = "email"
    else:
        user = User.objects.filter(phone=identifier).first()
        method = "sms"

    if user:
        otp_code = generate_otp()
        OTP.objects.filter(identifier=identifier).delete()
        OTP.objects.create(identifier=identifier, code=otp_code)
        send_otp(identifier, otp_code, method=method)
        
        return api_response(
            message=f"OTP sent to {method}.",
            status_code=status.HTTP_200_OK,
            request=request
        )
    
    return api_response(
        message="User not found.",
        success=False,
        status_code=status.HTTP_404_NOT_FOUND,
        request=request
    )

@api_view(['POST'])
def password_reset_confirm(request):
    serializer = PasswordResetConfirmSerializer(data=request.data, context={'request': request})
    
    username = request.data.get('username')
    otp_code = request.data.get('otp')
    
    try:
        user = User.objects.get(username=username)
        dest = user.email if user.email else user.phone
        otp_record = OTP.objects.filter(identifier=dest, code=otp_code).last()
        
        if otp_record and otp_record.is_valid():
            if serializer.is_valid():
                serializer.save()
                return api_response(
                    message="Password reset successfully.",
                    status_code=status.HTTP_200_OK,
                    request=request
                )
    except User.DoesNotExist:
        pass

    return api_response(
        message="Invalid OTP or Data",
        success=False,
        status_code=status.HTTP_400_BAD_REQUEST,
        request=request
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_profile(request):
    serializer = ProfileSerializer(request.user, context={'request': request})
    return api_response(
        message="Profile fetched successfully.",
        data=serializer.data,
        status_code=status.HTTP_200_OK,
        request=request
    )

@api_view(['PUT'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def update_profile(request):
    serializer = ProfileSerializer(request.user, data=request.data, partial=True, context={'request': request})
    if serializer.is_valid():
        serializer.save()
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

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password(request):
    serializer = PasswordChangeSerializer(data=request.data, context={'request': request})
    if serializer.is_valid():
        serializer.save()
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

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_view(request):
    serializer = LogoutSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
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

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_account(request):
    serializer = DeleteAccountSerializer(data=request.data, context={'request': request})
    if serializer.is_valid():
        serializer.save()
        return api_response(
            message="Account deleted successfully.",
            status_code=status.HTTP_204_NO_CONTENT,
            request=request
        )
    return api_response(
        message="Validation failed",
        data=serializer.errors,
        success=False,
        status_code=status.HTTP_400_BAD_REQUEST,
        request=request
    )