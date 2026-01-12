from django.urls import path
from .views import (
    signup_initiate, signup_verify, signup_finalize,
    MyTokenObtainPairView, get_profile, 
    update_profile, password_reset_request, 
    password_reset_confirm, change_password, 
    logout_view, delete_account,resend_otp,
    initiate_email_change, verify_email_change,
    resend_email_change_otp

)

urlpatterns = [
    path('signup/initiate/', signup_initiate, name='signup-initiate'),
    path('signup/verify/', signup_verify, name='signup-verify'),
    path('signup/finalize/', signup_finalize, name='signup-finalize'),
    path('login/', MyTokenObtainPairView.as_view(), name='login'),
    path('logout/', logout_view, name='logout'),
    path('profile/', get_profile, name='profile'),
    path('profile/update/', update_profile, name='profile-update'),
    path('password-reset/request/', password_reset_request, name='password-reset-request'),
    path('password-reset/confirm/', password_reset_confirm, name='password-reset-confirm'),
    path('password-change/', change_password, name='password-change'),
    path('delete-account/', delete_account, name='delete-account'),
    path('resend-otp/', resend_otp, name='resend-otp'),
    path('change-email/initiate/', initiate_email_change, name='change-email-initiate'),
    path('change-email/verify/', verify_email_change, name='change-email-verify'),
    path('change-email/resend/', resend_email_change_otp, name='change-email-resend'),]