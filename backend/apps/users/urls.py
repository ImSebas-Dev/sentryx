from django.urls import path
from apps.users.views import (
    ShieldTokenObtainPairView, ShieldTokenRefreshView, LogoutView, UserMeView, UserListView,
    RegisterView, VerifyEmailView, ResendVerificationView,
    PasswordResetRequestView, PasswordResetConfirmView,
)
from apps.users.mfa_views import (
    MFASetupView, MFAEnableView, MFADisableView, MFAVerifyView, MFAAdminResetView,
)

urlpatterns = [
    # Auth
    path("token/",                    ShieldTokenObtainPairView.as_view(), name="token_obtain"),
    path("token/refresh/",            ShieldTokenRefreshView.as_view(),    name="token_refresh"),
    path("logout/",                   LogoutView.as_view(),                name="logout"),
    # Verificación en dos pasos (TOTP)
    path("mfa/setup/",                MFASetupView.as_view(),              name="mfa_setup"),
    path("mfa/enable/",               MFAEnableView.as_view(),             name="mfa_enable"),
    path("mfa/disable/",              MFADisableView.as_view(),            name="mfa_disable"),
    path("mfa/verify/",               MFAVerifyView.as_view(),             name="mfa_verify"),
    # Registro y verificación
    path("register/",                 RegisterView.as_view(),              name="register"),
    path("verify-email/",             VerifyEmailView.as_view(),           name="verify_email"),
    path("resend-verification/",      ResendVerificationView.as_view(),    name="resend_verification"),
    # Recuperación de contraseña
    path("password-reset/",           PasswordResetRequestView.as_view(),  name="password_reset"),
    path("password-reset/confirm/",   PasswordResetConfirmView.as_view(),  name="password_reset_confirm"),
    # Perfil y admin
    path("me/",                       UserMeView.as_view(),                name="user_me"),
    path("users/",                    UserListView.as_view(),              name="user_list"),
    path("users/<uuid:user_id>/mfa/reset/", MFAAdminResetView.as_view(),   name="user_mfa_reset"),
]
