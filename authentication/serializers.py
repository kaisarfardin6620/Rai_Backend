import re
from rest_framework import serializers
from .models import User, OTP
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from Rai_Backend import settings

class PasswordValidator:
    @staticmethod
    def validate_password_strength(password):
        has_length = len(password) >= 8
        has_digit = re.search(r"\d", password)
        if not (has_length and has_digit):
            raise serializers.ValidationError(
                ("Password must be at least 8 characters and contain a number.")
            )

class SignupInitiateSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        email = attrs.get('email')
        phone = attrs.get('phone')
        
        if not email and not phone:
            raise serializers.ValidationError("Provide either email or phone.")
        
        if email and User.objects.filter(email=email).exists():
            raise serializers.ValidationError({"email": "Email already registered. Please login."})
        
        if phone and User.objects.filter(phone=phone).exists():
            raise serializers.ValidationError({"phone": "Phone already registered. Please login."})
            
        return attrs

class SignupVerifySerializer(serializers.Serializer):
    identifier = serializers.CharField() 
    otp = serializers.CharField(max_length=6)

class SignupFinalizeSerializer(serializers.ModelSerializer):
    identifier = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True, validators=[PasswordValidator.validate_password_strength])
    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)
    bio = serializers.CharField(required=False, allow_blank=True)
    date_of_birth = serializers.DateField(required=False)
    profile_picture = serializers.ImageField(required=False)

    class Meta:
        model = User
        fields = [
            'identifier', 'username', 'password', 
            'first_name', 'last_name', 'bio', 
            'date_of_birth', 'profile_picture'
        ]

    def validate(self, attrs):
        identifier = attrs.get('identifier')
        if '@' in identifier:
            if User.objects.filter(email=identifier).exists():
                raise serializers.ValidationError({"identifier": "This email is already registered."})
        else:
            if User.objects.filter(phone=identifier).exists():
                raise serializers.ValidationError({"identifier": "This phone number is already registered."})
        
        return attrs

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Username is already taken.")
        return value

    def create(self, validated_data):
        identifier = validated_data.pop('identifier')
        password = validated_data.pop('password')
        email = identifier if '@' in identifier else None
        phone = identifier if '@' not in identifier else None
        user = User.objects.create_user(
            username=validated_data['username'],
            email=email,
            phone=phone,
            password=password,
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            bio=validated_data.get('bio', ''),
            date_of_birth=validated_data.get('date_of_birth', None),
            profile_picture=validated_data.get('profile_picture', None),
            is_active=True,
            is_email_verified=bool(email),
            is_phone_verified=bool(phone)
        )
        return user

class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        return data

class ProfileSerializer(serializers.ModelSerializer):
    profile_picture = serializers.SerializerMethodField()
    class Meta:
        model = User
        fields = ['username', 'email', 'phone', 'profile_picture', 'date_of_birth', 'bio', 'first_name', 'last_name']

    def get_profile_picture(self, obj):
        if obj.profile_picture:
            return f"{settings.Server_Base_Url}{obj.profile_picture.url}"
        return None    

class PasswordResetRequestSerializer(serializers.Serializer):
    identifier = serializers.CharField(required=True)

class PasswordResetConfirmSerializer(serializers.Serializer):
    username = serializers.CharField()
    otp = serializers.CharField()
    new_password = serializers.CharField(validators=[PasswordValidator.validate_password_strength])
    confirm_new_password = serializers.CharField()

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_new_password']:
            raise serializers.ValidationError({"confirm_new_password": "Passwords do not match."})
        return attrs

    def save(self, **kwargs):
        user = User.objects.get(username=self.validated_data['username'])
        user.set_password(self.validated_data['new_password'])
        user.save()
        dest = user.email if user.email else user.phone
        OTP.objects.filter(identifier=dest).delete()
        return user

class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField()
    new_password = serializers.CharField(validators=[PasswordValidator.validate_password_strength])
    confirm_new_password = serializers.CharField()

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_new_password']:
            raise serializers.ValidationError("Passwords do not match.")
        
        user = self.context['request'].user
        if not user.check_password(attrs['old_password']):
            raise serializers.ValidationError({"old_password": "Wrong password."})
        return attrs

    def save(self, **kwargs):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save()
        return user

class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()
    
    def validate(self, attrs):
        self.token = attrs['refresh']
        return attrs

    def save(self, **kwargs):
        try:
            RefreshToken(self.token).blacklist()
        except Exception:
            pass 

class DeleteAccountSerializer(serializers.Serializer):
    password = serializers.CharField()

    def validate_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Incorrect password.")
        return value

    def save(self, **kwargs):
        user = self.context['request'].user
        user.delete()