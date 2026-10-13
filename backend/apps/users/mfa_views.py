"""
Sentryx v2 — Endpoints de autenticación de dos factores (TOTP).

  POST /api/v1/auth/mfa/setup/    Genera secreto y QR (no activa nada)
  POST /api/v1/auth/mfa/enable/   Confirma con un código y entrega 8 códigos de recuperación
  POST /api/v1/auth/mfa/disable/  Exige contraseña y código
  POST /api/v1/auth/mfa/verify/   Segundo paso del login: canjea mfa_token por JWT
  POST /api/v1/auth/users/<id>/mfa/reset/   Admin restablece el 2FA de otro usuario

Cada evento queda en AuditLog con resource="mfa" y detail.event.
"""
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_login_failed
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from drf_spectacular.utils import (
    extend_schema, inline_serializer, OpenApiExample, OpenApiParameter, OpenApiResponse,
)
from drf_spectacular.types import OpenApiTypes

from apps.audit.models import AuditLog
from apps.users import mfa
from apps.users.permissions import IsAdminUser
from apps.users.serializers import issue_tokens

User = get_user_model()
logger = logging.getLogger(__name__)

NOT_CONFIGURED = Response(
    {"error": "La verificación en dos pasos no está configurada en el servidor "
              "(falta MFA_ENCRYPTION_KEY).",
     "code": "mfa_not_configured"},
    status=status.HTTP_503_SERVICE_UNAVAILABLE,
)


def client_ip(request):
    return (request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
            or request.META.get("REMOTE_ADDR", ""))


def audit(request, action, event, user, **detail):
    AuditLog.log(action=action, resource="mfa", resource_id=str(user.pk) if user else "",
                 user=user, ip=client_ip(request), detail={"event": event, **detail})


class MFAThrottle(ScopedRateThrottle):
    scope_attr = "throttle_scope"


# ── Serializers ───────────────────────────────────────────
class MFASetupResponseSerializer(serializers.Serializer):
    secret      = serializers.CharField(help_text="Clave para ingresar a mano en la app")
    otpauth_url = serializers.CharField()
    qr_code     = serializers.CharField(help_text="PNG en data URI para un <img>")


class MFACodeSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=12, help_text="Código TOTP de 6 dígitos")


class MFAEnableResponseSerializer(serializers.Serializer):
    recovery_codes = serializers.ListField(child=serializers.CharField(),
                                           help_text="Se muestran una sola vez")
    access  = serializers.CharField(required=False)
    refresh = serializers.CharField(required=False)


class MFADisableSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True)
    code     = serializers.CharField(max_length=20,
                                     help_text="Código TOTP o código de recuperación")


class MFAVerifySerializer(serializers.Serializer):
    mfa_token     = serializers.CharField()
    code          = serializers.CharField(max_length=12, required=False, allow_blank=True)
    recovery_code = serializers.CharField(max_length=20, required=False, allow_blank=True)

    def validate(self, data):
        if not data.get("code") and not data.get("recovery_code"):
            raise serializers.ValidationError("Envía code o recovery_code.")
        return data


class TokenPairSerializer(serializers.Serializer):
    access  = serializers.CharField()
    refresh = serializers.CharField()


# ── Views ─────────────────────────────────────────────────
@extend_schema(tags=["mfa"], summary="Generar secreto y QR (no activa el 2FA)",
               request=None, responses={200: MFASetupResponseSerializer})
class MFASetupView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes   = [MFAThrottle]
    throttle_scope     = "mfa"
    serializer_class   = MFASetupResponseSerializer

    def post(self, request):
        if not mfa.is_configured():
            return NOT_CONFIGURED
        if request.user.mfa_enabled:
            return Response({"error": "La verificación en dos pasos ya está activa."},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(mfa.start_setup(request.user))


@extend_schema(tags=["mfa"], summary="Activar el 2FA con un código",
               request=MFACodeSerializer, responses={200: MFAEnableResponseSerializer},
               examples=[OpenApiExample("Código", request_only=True, value={"code": "492039"})])
class MFAEnableView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes   = [MFAThrottle]
    throttle_scope     = "mfa"
    serializer_class   = MFACodeSerializer

    def post(self, request):
        if not mfa.is_configured():
            return NOT_CONFIGURED
        user = request.user
        if user.mfa_enabled:
            return Response({"error": "La verificación en dos pasos ya está activa."},
                            status=status.HTTP_400_BAD_REQUEST)
        if not user.mfa_secret:
            return Response({"error": "Primero genera el código QR."},
                            status=status.HTTP_400_BAD_REQUEST)

        ser = MFACodeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        if not mfa.verify_totp(user, ser.validated_data["code"]):
            audit(request, AuditLog.Action.LOGIN_FAILED, "mfa_enable_failed", user)
            return Response({"error": "El código no es válido. Revisa la hora del "
                                      "teléfono y escribe el código actual.",
                             "code": "mfa_invalid_code"},
                            status=status.HTTP_400_BAD_REQUEST)

        had_setup_claim = bool(request.auth and request.auth.get("mfa_setup_required"))
        codes = mfa.enable(user)
        audit(request, AuditLog.Action.CONFIG_CHANGE, "mfa_enabled", user)

        body = {"recovery_codes": codes}
        # El token actual sigue marcado con mfa_setup_required: entregar uno
        # limpio para que el admin pueda seguir sin cerrar sesión.
        if had_setup_claim:
            body.update(issue_tokens(user))
        return Response(body)


@extend_schema(tags=["mfa"], summary="Desactivar el 2FA (contraseña + código)",
               request=MFADisableSerializer,
               responses={200: inline_serializer("MFAMessage", {"message": serializers.CharField()})})
class MFADisableView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes   = [MFAThrottle]
    throttle_scope     = "mfa"
    serializer_class   = MFADisableSerializer

    def post(self, request):
        if not mfa.is_configured():
            return NOT_CONFIGURED
        user = request.user
        if not user.mfa_enabled:
            return Response({"error": "La verificación en dos pasos no está activa."},
                            status=status.HTTP_400_BAD_REQUEST)
        if user.is_admin and settings.MFA_REQUIRED_FOR_ADMINS:
            return Response({"error": "La política de seguridad exige que los "
                                      "administradores mantengan el 2FA activo."},
                            status=status.HTTP_403_FORBIDDEN)

        ser = MFADisableSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        # Validar la contraseña primero: si va antes el código, un código de
        # recuperación se gastaría aunque la contraseña sea incorrecta.
        ok = user.check_password(d["password"]) and (
            mfa.verify_totp(user, d["code"])
            or mfa.consume_recovery_code(user, d["code"]) is not None
        )
        if not ok:
            audit(request, AuditLog.Action.LOGIN_FAILED, "mfa_disable_failed", user)
            return Response({"error": "La contraseña o el código no son correctos."},
                            status=status.HTTP_400_BAD_REQUEST)

        mfa.disable(user)
        audit(request, AuditLog.Action.CONFIG_CHANGE, "mfa_disabled", user)
        return Response({"message": "Verificación en dos pasos desactivada."})


@extend_schema(
    tags=["mfa"], summary="Iniciar sesión (paso 2): canjear mfa_token por JWT",
    request=MFAVerifySerializer,
    responses={
        200: TokenPairSerializer,
        400: OpenApiResponse(description="Código incorrecto; incluye attempts_left."),
        401: OpenApiResponse(description="mfa_token expirado, inválido, ya usado o sin intentos."),
        429: OpenApiResponse(description="Límite por IP o bloqueo de django-axes."),
    },
    examples=[
        OpenApiExample("Código TOTP", request_only=True,
                       value={"mfa_token": "eyJ1aWQiOi…", "code": "492039"}),
        OpenApiExample("Código de recuperación", request_only=True,
                       value={"mfa_token": "eyJ1aWQiOi…", "recovery_code": "k7m2p-x9q4r"}),
    ],
)
class MFAVerifyView(APIView):
    """
    Segundo paso del login. Sin autenticación JWT: la identidad viene del
    mfa_token firmado. Límites: MFA_MAX_ATTEMPTS por token, throttle "mfa" por
    IP y los fallos cuentan para django-axes como un login fallido.
    """
    permission_classes     = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes       = [MFAThrottle]
    throttle_scope         = "mfa"
    serializer_class       = MFAVerifySerializer

    def post(self, request):
        from axes.handlers.proxy import AxesProxyHandler

        # axes trabaja con el HttpRequest de Django, no con el Request de DRF
        http_request = request._request

        if not mfa.is_configured():
            return NOT_CONFIGURED
        ser = MFAVerifySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        try:
            payload = mfa.read_login_token(d["mfa_token"])
            user = User.objects.filter(pk=payload["uid"], is_active=True).first()
            if user is None or not user.mfa_enabled:
                raise mfa.MFATokenError("mfa_token_invalid",
                                        "La verificación no es válida. Inicia sesión de nuevo.")
            credentials = {settings.AXES_USERNAME_FORM_FIELD: user.email}
            if not AxesProxyHandler.is_allowed(http_request, credentials):
                return Response({"error": "Cuenta bloqueada temporalmente por demasiados "
                                          "intentos fallidos.", "code": "account_locked"},
                                status=status.HTTP_429_TOO_MANY_REQUESTS)
            attempt = mfa.register_attempt(payload)
        except mfa.MFATokenError as exc:
            audit(request, AuditLog.Action.LOGIN_FAILED, "mfa_token_rejected", None,
                  reason=exc.code)
            return Response({"error": exc.message, "code": exc.code},
                            status=status.HTTP_401_UNAUTHORIZED)

        used_recovery = bool(d.get("recovery_code"))
        remaining_codes = None
        if used_recovery:
            remaining_codes = mfa.consume_recovery_code(user, d["recovery_code"])
            ok = remaining_codes is not None
        else:
            ok = mfa.verify_totp(user, d["code"])

        if not ok:
            left = settings.MFA_MAX_ATTEMPTS - attempt
            audit(request, AuditLog.Action.LOGIN_FAILED, "mfa_verify_failed", user,
                  attempt=attempt, method="recovery_code" if used_recovery else "totp")
            # Contar el fallo en axes igual que una contraseña incorrecta
            user_login_failed.send(sender=__name__, credentials=credentials,
                                   request=http_request)
            if left <= 0:
                mfa.consume_login_token(payload)
                return Response({"error": "Demasiados códigos incorrectos. "
                                          "Inicia sesión de nuevo.",
                                 "code": "mfa_too_many_attempts"},
                                status=status.HTTP_401_UNAUTHORIZED)
            return Response({"error": "El código no es válido.",
                             "code": "mfa_invalid_code", "attempts_left": left},
                            status=status.HTTP_400_BAD_REQUEST)

        # Consumir antes de entregar tokens: si dos peticiones llegan a la vez
        # con el mismo mfa_token, solo una obtiene el JWT.
        if not mfa.consume_login_token(payload):
            return Response({"error": "Esta verificación ya se usó. Inicia sesión de nuevo.",
                             "code": "mfa_token_used"},
                            status=status.HTTP_401_UNAUTHORIZED)

        if used_recovery:
            audit(request, AuditLog.Action.LOGIN, "mfa_recovery_code_used", user,
                  remaining=remaining_codes)
        AuditLog.log(AuditLog.Action.LOGIN, "auth", user=user, ip=client_ip(request),
                     detail={"mfa": True})
        AxesProxyHandler.reset_attempts(username=user.email)

        body = issue_tokens(user)
        if used_recovery:
            body["recovery_codes_remaining"] = remaining_codes
        return Response(body)


@extend_schema(tags=["mfa"], summary="Restablecer el 2FA de otro usuario (admin)", request=None,
               responses={200: inline_serializer("MFAResetResponse", {
                   "message": serializers.CharField(), "user_id": serializers.UUIDField()})})
class MFAAdminResetView(APIView):
    """Un admin desactiva el 2FA de otro usuario (p. ej. si perdió el teléfono)."""
    permission_classes = [IsAdminUser]

    def post(self, request, user_id):
        target = User.objects.filter(pk=user_id).first()
        if target is None:
            return Response({"error": "Usuario no encontrado."},
                            status=status.HTTP_404_NOT_FOUND)
        if target.pk == request.user.pk:
            return Response({"error": "Para tu propia cuenta usa «Desactivar» en "
                                      "Seguridad de la cuenta."},
                            status=status.HTTP_400_BAD_REQUEST)
        was_enabled = target.mfa_enabled
        mfa.disable(target)
        audit(request, AuditLog.Action.CONFIG_CHANGE, "mfa_reset_by_admin", request.user,
              target_user=str(target.pk), target_email=target.email,
              was_enabled=was_enabled)
        return Response({"message": f"Se restableció la verificación en dos pasos de "
                                    f"{target.email}.", "user_id": str(target.pk)})
