"""
Sentryx v2 — Views de autenticación ampliadas.
Registro por correo, verificación, aprobación admin, recuperación de contraseña.
"""
import logging
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status, permissions, generics
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from drf_spectacular.utils import (
    extend_schema, inline_serializer, OpenApiExample, OpenApiParameter, OpenApiResponse,
)
from drf_spectacular.types import OpenApiTypes
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.users.email_service import (
    send_verification_email, send_approval_notification,
    send_pending_approval_email, send_admin_new_user_alert,
    send_password_reset_email,
)
from apps.users.serializers import (
    ShieldTokenObtainPairSerializer, UserMeSerializer, UserListSerializer,
    issue_tokens,
)
from apps.users.permissions import IsAdminUser, IsAnalystOrAbove
from apps.audit.models import AuditLog

User = get_user_model()
logger = logging.getLogger(__name__)


# ── Serializers de registro ───────────────────────────────
class RegisterSerializer(serializers.Serializer):
    email        = serializers.EmailField()
    password     = serializers.CharField(min_length=10, write_only=True)
    organization = serializers.CharField(max_length=120, required=False, allow_blank=True)
    accepted_terms = serializers.BooleanField()

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Ya existe una cuenta con este correo.")
        return value.lower()

    def validate_accepted_terms(self, value):
        if not value:
            raise serializers.ValidationError(
                "Debes aceptar los Términos y Condiciones para registrarte."
            )
        return value


class MessageResponseSerializer(serializers.Serializer):
    """Respuesta genérica {"message": ...} (solo para la documentación OpenAPI)."""
    message = serializers.CharField()


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    email       = serializers.EmailField()
    token       = serializers.CharField()
    new_password= serializers.CharField(min_length=10, write_only=True)


class ApproveUserSerializer(serializers.Serializer):
    user_id  = serializers.UUIDField()
    approved = serializers.BooleanField()


# ── Views ─────────────────────────────────────────────────
@extend_schema(tags=["auth"], request=RegisterSerializer, responses={201: inline_serializer(
    "RegisterResponse", {"message": serializers.CharField(), "email": serializers.EmailField()})})
class RegisterView(APIView):
    """
    POST /api/v1/auth/register/
    Registro abierto. Crea cuenta inactiva hasta verificación + aprobación.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        ser = RegisterSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        # Generar username del email (parte antes del @)
        base_username = d["email"].split("@")[0].replace(".", "_")[:30]
        username = base_username
        n = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{n}"
            n += 1

        user = User.objects.create_user(
            username      = username,
            email         = d["email"],
            password      = d["password"],
            organization  = d.get("organization", ""),
            role          = User.Role.ANALYST,
            is_active     = True,        # activo pero sin acceso hasta aprobación
            is_approved   = False,
            is_email_verified = False,
            accepted_terms    = True,
            accepted_terms_at = timezone.now(),
        )

        # Enviar correo de verificación
        sent = send_verification_email(user)
        if not sent:
            logger.error(f"[Register] No se pudo enviar correo a {user.email}")

        # Notificar a todos los admins
        admins = User.objects.filter(role=User.Role.ADMIN, is_active=True)
        for admin in admins:
            send_admin_new_user_alert(user, admin.email)

        return Response({
            "message": (
                "Cuenta creada. Revisa tu correo para verificar tu dirección. "
                "Una vez verificada, un administrador revisará tu solicitud."
            ),
            "email": user.email,
        }, status=status.HTTP_201_CREATED)


@extend_schema(tags=["auth"], request=inline_serializer("VerifyEmailRequest", {
    "email": serializers.EmailField(), "token": serializers.CharField()}), responses={200: MessageResponseSerializer})
class VerifyEmailView(APIView):
    """
    POST /api/v1/auth/verify-email/
    Verifica el token del correo de confirmación.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get("email", "").lower()
        token = request.data.get("token", "")

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({"error": "Datos inválidos."},
                            status=status.HTTP_400_BAD_REQUEST)

        if user.is_email_verified:
            return Response({"message": "El correo ya fue verificado anteriormente."})

        if not user.is_verification_token_valid(token):
            return Response({
                "error": "El enlace de verificación es inválido o expiró. "
                         "Solicita uno nuevo."
            }, status=status.HTTP_400_BAD_REQUEST)

        user.is_email_verified = True
        user.email_verification_token = ""
        user.save(update_fields=["is_email_verified", "email_verification_token"])

        send_pending_approval_email(user)

        return Response({
            "message": "Correo verificado. Tu cuenta está pendiente de aprobación por el administrador.",
            "pending_approval": True,
        })


@extend_schema(tags=["auth"], request=PasswordResetRequestSerializer, responses={200: MessageResponseSerializer})
class ResendVerificationView(APIView):
    """POST /api/v1/auth/resend-verification/ — Reenvía el correo de verificación."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get("email", "").lower()
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # No revelar si el email existe
            return Response({"message": "Si el correo existe, recibirás un nuevo enlace."})

        if user.is_email_verified:
            return Response({"message": "Tu correo ya está verificado."})

        send_verification_email(user)
        return Response({"message": "Si el correo existe, recibirás un nuevo enlace."})


@extend_schema(tags=["auth"], request=PasswordResetRequestSerializer, responses={200: MessageResponseSerializer})
class PasswordResetRequestView(APIView):
    """POST /api/v1/auth/password-reset/ — Solicitar recuperación de contraseña."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        ser = PasswordResetRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        email = ser.validated_data["email"].lower()

        try:
            user = User.objects.get(email=email, is_email_verified=True)
            send_password_reset_email(user)
        except User.DoesNotExist:
            pass  # No revelar si el email existe

        return Response({
            "message": "Si el correo está registrado y verificado, "
                       "recibirás un enlace para restablecer tu contraseña."
        })


@extend_schema(tags=["auth"], request=PasswordResetConfirmSerializer, responses={200: MessageResponseSerializer})
class PasswordResetConfirmView(APIView):
    """POST /api/v1/auth/password-reset/confirm/ — Confirmar nueva contraseña."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        ser = PasswordResetConfirmSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        try:
            user = User.objects.get(email=d["email"].lower())
        except User.DoesNotExist:
            return Response({"error": "Datos inválidos."},
                            status=status.HTTP_400_BAD_REQUEST)

        if not user.is_reset_token_valid(d["token"]):
            return Response({
                "error": "El enlace de recuperación es inválido o expiró. "
                         "Solicita uno nuevo."
            }, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(d["new_password"])
        user.clear_reset_token()

        AuditLog.log(
            action=AuditLog.Action.UPDATE,
            resource="auth",
            resource_id=str(user.pk),
            user=user,
            detail={"action": "password_reset"},
        )
        return Response({"message": "Contraseña restablecida exitosamente."})


@extend_schema(tags=["auth"], request=ApproveUserSerializer, responses={200: MessageResponseSerializer})
class ApproveUserView(APIView):
    """
    POST /api/v1/auth/users/approve/
    Admin aprueba o rechaza una cuenta pendiente.
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        ser = ApproveUserSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        try:
            user = User.objects.get(pk=ser.validated_data["user_id"])
        except User.DoesNotExist:
            return Response({"error": "Usuario no encontrado."},
                            status=status.HTTP_404_NOT_FOUND)

        if not user.is_email_verified:
            return Response({
                "error": "El usuario aún no ha verificado su correo."
            }, status=status.HTTP_400_BAD_REQUEST)

        approved = ser.validated_data["approved"]
        user.is_approved = approved

        if not approved:
            user.is_active = False   # desactivar si se rechaza

        user.save(update_fields=["is_approved", "is_active"])

        if approved:
            send_approval_notification(user)

        AuditLog.log(
            action=AuditLog.Action.UPDATE,
            resource="users",
            resource_id=str(user.pk),
            user=request.user,
            detail={"approved": approved, "target_email": user.email},
        )

        return Response({
            "message": f"Cuenta {'aprobada' if approved else 'rechazada'}.",
            "user_id": str(user.pk),
            "is_approved": approved,
        })


@extend_schema(tags=["auth"])
class PendingUsersView(generics.ListAPIView):
    """GET /api/v1/auth/users/pending/ — Lista de cuentas pendientes de aprobación."""
    permission_classes = [IsAdminUser]
    serializer_class   = UserListSerializer

    def get_queryset(self):
        return User.objects.filter(
            is_email_verified=True,
            is_approved=False,
            is_active=True,
        ).order_by("created_at")


@extend_schema(
    tags=["auth"],
    summary="Iniciar sesión (paso 1)",
    request=inline_serializer("LoginRequest", {
        "email": serializers.EmailField(), "password": serializers.CharField()}),
    responses={
        200: OpenApiResponse(
            response=inline_serializer("LoginResponse", {
                "access":       serializers.CharField(required=False),
                "refresh":      serializers.CharField(required=False),
                "mfa_required": serializers.BooleanField(required=False),
                "mfa_token":    serializers.CharField(required=False),
                "expires_in":   serializers.IntegerField(required=False),
                "mfa_setup_required": serializers.BooleanField(required=False),
            }),
            description="Par JWT, o desafío de 2FA si la cuenta lo tiene activo."),
        401: OpenApiResponse(description="Correo o contraseña incorrectos."),
        403: OpenApiResponse(description="Correo sin verificar o cuenta pendiente de aprobación."),
        429: OpenApiResponse(description="Cuenta o IP bloqueada por django-axes."),
    },
    examples=[
        OpenApiExample("Credenciales", request_only=True,
                       value={"email": "analista@sentryx.local", "password": "analista123"}),
        OpenApiExample("Sin 2FA", response_only=True,
                       value={"access": "eyJhbGciOi…", "refresh": "eyJhbGciOi…"}),
        OpenApiExample("Con 2FA", response_only=True,
                       value={"mfa_required": True, "mfa_token": "eyJ1aWQiOi…", "expires_in": 300}),
    ],
)
class ShieldTokenObtainPairView(TokenObtainPairView):
    """
    Login JWT — verifica que la cuenta esté verificada y aprobada.

    Con 2FA activo no entrega JWT: responde {"mfa_required": true,
    "mfa_token": ...} y el cliente debe llamar a /auth/mfa/verify/.
    Con MFA_REQUIRED_FOR_ADMINS=True, un admin sin 2FA recibe tokens con el
    claim mfa_setup_required que solo sirven para configurarlo.
    """
    serializer_class = ShieldTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        # Verificar estado de la cuenta ANTES del login
        email = request.data.get("email") or request.data.get("username", "")
        try:
            user = User.objects.get(email__iexact=email)
            if not user.is_email_verified:
                return Response({
                    "error": "Debes verificar tu correo antes de iniciar sesión.",
                    "code":  "email_not_verified",
                }, status=status.HTTP_403_FORBIDDEN)
            if not user.is_approved:
                return Response({
                    "error": "Tu cuenta está pendiente de aprobación por el administrador.",
                    "code":  "account_pending_approval",
                }, status=status.HTTP_403_FORBIDDEN)
        except User.DoesNotExist:
            pass  # Dejar que el serializer maneje el 401 normal

        # Comprobar el bloqueo de axes aquí: SimpleJWT pasa a authenticate()
        # el Request de DRF, axes marca el bloqueo sobre ese objeto y su
        # middleware no lo ve, así que sin esto la respuesta sería un 401
        # de "credenciales incorrectas" aunque la cuenta esté bloqueada.
        from axes.handlers.proxy import AxesProxyHandler
        if not AxesProxyHandler.is_allowed(request._request,
                                           {settings.AXES_USERNAME_FORM_FIELD: email}):
            return Response({
                "error": "Demasiados intentos fallidos. Espera unos minutos e "
                         "inténtalo de nuevo.",
                "code":  "account_locked",
            }, status=status.HTTP_429_TOO_MANY_REQUESTS)

        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as exc:
            raise InvalidToken(exc.args[0])
        user = serializer.user
        ip = (request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
              or request.META.get("REMOTE_ADDR", ""))

        # La contraseña es correcta. No devolver serializer.validated_data
        # (ya trae el JWT) cuando falta el segundo factor.
        if user.mfa_enabled:
            from apps.users import mfa
            if not mfa.is_configured():
                return Response({
                    "error": "La verificación en dos pasos no está disponible en el "
                             "servidor. Contacta al administrador.",
                    "code":  "mfa_not_configured",
                }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            AuditLog.log(AuditLog.Action.LOGIN, "mfa", resource_id=str(user.pk),
                         user=user, ip=ip, detail={"event": "mfa_challenge_issued"})
            return Response({
                "mfa_required": True,
                "mfa_token":    mfa.issue_login_token(user),
                "expires_in":   settings.MFA_LOGIN_TOKEN_MAX_AGE,
            })

        AuditLog.log(AuditLog.Action.LOGIN, "auth", user=user, ip=ip)
        if user.mfa_setup_required:
            body = issue_tokens(user, mfa_setup_required=True)
            body["mfa_setup_required"] = True
            return Response(body)
        return Response(serializer.validated_data)


@extend_schema(tags=["auth"])
class UserMeView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/v1/auth/me/"""
    serializer_class   = UserMeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


@extend_schema(tags=["auth"])
class UserListView(generics.ListAPIView):
    """GET /api/v1/auth/users/ — todos los usuarios (solo admin)."""
    serializer_class   = UserListSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        return User.objects.all().order_by("-created_at")
