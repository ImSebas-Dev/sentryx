"""
Sentryx v2 — Login del panel /admin/ con verificación en dos pasos.

El login por defecto de Django solo pide contraseña: una cuenta con 2FA podía
entrar al panel (que da acceso a todos los datos) sin el segundo factor. Este
formulario exige el código TOTP a quien tenga el 2FA activo y, si la política
MFA_REQUIRED_FOR_ADMINS está activa, no deja entrar a nadie sin 2FA.
"""
from django import forms
from django.conf import settings
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth.signals import user_login_failed
from django.core.exceptions import ValidationError

from apps.audit.utils import log_security_event


class MFAAdminAuthenticationForm(AdminAuthenticationForm):
    otp_code = forms.CharField(
        label="Código de verificación (2FA)", required=False, max_length=12, strip=True,
        widget=forms.TextInput(attrs={"autocomplete": "one-time-code", "inputmode": "numeric"}),
    )

    def confirm_login_allowed(self, user):
        # Comprueba is_active e is_staff
        super().confirm_login_allowed(user)
        if not user.is_email_verified:
            raise ValidationError("Verifica tu correo antes de entrar.", code="email_not_verified")

        from apps.users import mfa
        if user.mfa_enabled:
            if not mfa.is_configured():
                raise ValidationError("La verificación en dos pasos no está configurada en el servidor.",
                                      code="mfa_not_configured")
            if not mfa.verify_totp(user, self.cleaned_data.get("otp_code")):
                # Cuenta para django-axes igual que una contraseña incorrecta
                user_login_failed.send(sender=__name__, credentials={
                    settings.AXES_USERNAME_FORM_FIELD: user.email}, request=self.request)
                log_security_event("admin_mfa_failed", self.request, user=str(user.pk))
                raise ValidationError("El código de verificación no es correcto.", code="invalid_otp")
        elif settings.MFA_REQUIRED_FOR_ADMINS:
            raise ValidationError(
                "Activa la verificación en dos pasos en Sentryx (Seguridad de la cuenta) "
                "antes de entrar al panel de administración.", code="mfa_setup_required")
