"""
Sentryx v2 — Views de autenticación ampliadas.
Registro por correo, verificación, recuperación de contraseña, renovación del
token y cierre de sesión.

Reglas para quien toque este módulo:
  - Ninguna respuesta debe revelar si un correo tiene cuenta (enumeración).
  - Toda contraseña nueva pasa por validate_password (AUTH_PASSWORD_VALIDATORS).
  - Todo endpoint que entregue tokens usa cookies.token_response().
"""
import logging
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import status, permissions, generics
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from drf_spectacular.utils import (
    extend_schema, inline_serializer, OpenApiExample, OpenApiResponse,
)
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.audit.models import AuditLog
from apps.audit.utils import client_ip, log_security_event
from apps.users import cookies
from apps.users.email_service import (
    send_notification, send_verification_email, send_password_reset_email,
)
from apps.users.organization import org_of
from apps.users.serializers import (
    ShieldTokenObtainPairSerializer, UserMeSerializer, UserListSerializer,
    issue_tokens,
)
from apps.users.permissions import IsAdminUser

User = get_user_model()
logger = logging.getLogger(__name__)

GENERIC_REGISTER_MESSAGE = (
    "Cuenta creada. Revisa tu correo para verificar tu dirección. "
    "Una vez verificada, ya puedes iniciar sesión."
)


class AuthThrottle(ScopedRateThrottle):
    """Límite por IP (anónimos) del scope definido en cada vista."""


def _password_errors(password, user=None):
    try:
        validate_password(password, user=user)
    except DjangoValidationError as exc:
        return list(exc.messages)
    return []


# ── Serializers de registro ───────────────────────────────
class RegisterSerializer(serializers.Serializer):
    email        = serializers.EmailField(max_length=254)
    password     = serializers.CharField(min_length=10, max_length=128, write_only=True,
                                         trim_whitespace=False)
    organization = serializers.CharField(max_length=120, required=False, allow_blank=True)
    accepted_terms = serializers.BooleanField()

    def validate_email(self, value):
        return value.strip().lower()

    def validate_accepted_terms(self, value):
        if not value:
            raise serializers.ValidationError(
                "Debes aceptar los Términos y Condiciones para registrarte."
            )
        return value

    def validate(self, data):
        # Mismas reglas que el resto de Django: longitud, comunes, solo números
        # y parecido al correo. Se valida contra un usuario temporal sin guardar.
        errors = _password_errors(data["password"], User(email=data["email"]))
        if errors:
            raise serializers.ValidationError({"password": errors})
        return data


class MessageResponseSerializer(serializers.Serializer):
    """Respuesta genérica {"message": ...} (solo para la documentación OpenAPI)."""
    message = serializers.CharField()


class EmailOnlySerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)


class VerifyEmailSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    token = serializers.CharField(max_length=128)


class PasswordResetConfirmSerializer(serializers.Serializer):
    email        = serializers.EmailField(max_length=254)
    token        = serializers.CharField(max_length=128)
    new_password = serializers.CharField(min_length=10, max_length=128, write_only=True,
                                         trim_whitespace=False)


def claimable_organization(name: str) -> str:
    """
    Devuelve la organización que puede tomar una cuenta nueva. Nadie revisa el
    registro y la organización da acceso a los datos de la empresa, así que un
    nombre ya usado queda vacío: un admin agrega a la persona desde /admin/.
    No avises en la respuesta que el nombre existe: revelaría qué empresas son clientes.
    """
    name = (name or "").strip()
    if name and User.objects.filter(organization__iexact=name).exists():
        return ""
    return name


def revoke_refresh_tokens(user) -> int:
    """Pone en la lista negra todos los refresh tokens vigentes del usuario."""
    from rest_framework_simplejwt.token_blacklist.models import (
        BlacklistedToken, OutstandingToken,
    )
    revoked = 0
    for outstanding in OutstandingToken.objects.filter(user=user, expires_at__gt=timezone.now()):
        _, created = BlacklistedToken.objects.get_or_create(token=outstanding)
        revoked += int(created)
    return revoked


# ── Views ─────────────────────────────────────────────────
@extend_schema(tags=["auth"], request=RegisterSerializer, responses={201: inline_serializer(
    "RegisterResponse", {"message": serializers.CharField(), "email": serializers.EmailField()})})
class RegisterView(APIView):
    """
    POST /api/v1/auth/register/
    Registro abierto. La cuenta no puede iniciar sesión hasta verificar el correo.
    Si el correo ya tiene cuenta responde igual (no revela qué correos existen)
    y avisa por correo al dueño de la cuenta.
    """
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes   = [AuthThrottle]
    throttle_scope     = "auth_register"

    def post(self, request):
        ser = RegisterSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        existing = User.objects.filter(email__iexact=d["email"]).first()
        if existing is not None:
            log_security_event("register_existing_email", request)
            send_notification(
                existing.email, "Intento de registro con tu correo — Sentryx",
                "<p>Alguien intentó crear una cuenta en Sentryx con tu correo. Ya tienes "
                "una cuenta: si olvidaste la contraseña, usa «¿Olvidaste tu contraseña?». "
                "Si no fuiste tú, puedes ignorar este mensaje.</p>",
            )
            return Response({"message": GENERIC_REGISTER_MESSAGE, "email": d["email"]},
                            status=status.HTTP_201_CREATED)

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
            organization  = claimable_organization(d.get("organization", "")),
            role          = User.Role.ANALYST,
            is_active     = True,        # activo pero sin acceso hasta verificar el correo
            is_email_verified = False,
            accepted_terms    = True,
            accepted_terms_at = timezone.now(),
        )

        if not send_verification_email(user):
            logger.error("[Register] No se pudo enviar el correo de verificación (user=%s)", user.pk)

        return Response({"message": GENERIC_REGISTER_MESSAGE, "email": user.email},
                        status=status.HTTP_201_CREATED)


@extend_schema(tags=["auth"], request=VerifyEmailSerializer, responses={200: MessageResponseSerializer})
class VerifyEmailView(APIView):
    """
    POST /api/v1/auth/verify-email/
    Verifica el token del correo de confirmación (un solo uso, caduca).
    """
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes   = [AuthThrottle]
    throttle_scope     = "auth_login"

    def post(self, request):
        ser = VerifyEmailSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        email = ser.validated_data["email"].lower()
        token = ser.validated_data["token"]
        invalid = Response({
            "error": "El enlace de verificación es inválido o expiró. Solicita uno nuevo."
        }, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            return invalid
        if user.is_email_verified:
            return Response({"message": "El correo ya fue verificado anteriormente."})
        if not user.is_verification_token_valid(token):
            log_security_event("verify_email_invalid_token", request)
            return invalid

        user.is_email_verified = True
        user.email_verification_token = ""
        user.save(update_fields=["is_email_verified", "email_verification_token"])

        return Response({"message": "Correo verificado. Ya puedes iniciar sesión."})


@extend_schema(tags=["auth"], request=EmailOnlySerializer, responses={200: MessageResponseSerializer})
class ResendVerificationView(APIView):
    """POST /api/v1/auth/resend-verification/ — Reenvía el correo de verificación."""
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes   = [AuthThrottle]
    throttle_scope     = "auth_email"
    GENERIC = {"message": "Si el correo existe y no está verificado, recibirás un nuevo enlace."}

    def post(self, request):
        ser = EmailOnlySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = User.objects.filter(email__iexact=ser.validated_data["email"]).first()
        # Misma respuesta en todos los casos: no revelar si la cuenta existe
        if (user is not None and not user.is_email_verified
                and not user.email_cooldown_active(user.email_verification_sent_at)):
            send_verification_email(user)
        return Response(self.GENERIC)


@extend_schema(tags=["auth"], request=EmailOnlySerializer, responses={200: MessageResponseSerializer})
class PasswordResetRequestView(APIView):
    """POST /api/v1/auth/password-reset/ — Solicitar recuperación de contraseña."""
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes   = [AuthThrottle]
    throttle_scope     = "auth_email"

    def post(self, request):
        ser = EmailOnlySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        email = ser.validated_data["email"].lower()

        user = User.objects.filter(email__iexact=email, is_email_verified=True,
                                   is_active=True).first()
        if user is not None and not user.email_cooldown_active(user.password_reset_sent_at):
            send_password_reset_email(user)
            AuditLog.log(AuditLog.Action.UPDATE, "auth", user=user, resource_id=str(user.pk),
                         ip=client_ip(request), detail={"event": "password_reset_requested"})

        return Response({
            "message": "Si el correo está registrado y verificado, "
                       "recibirás un enlace para restablecer tu contraseña."
        })


@extend_schema(tags=["auth"], request=PasswordResetConfirmSerializer, responses={200: MessageResponseSerializer})
class PasswordResetConfirmView(APIView):
    """
    POST /api/v1/auth/password-reset/confirm/ — Confirmar nueva contraseña.
    El enlace es de un solo uso, caduca en PASSWORD_RESET_TIMEOUT_MINUTES y al
    usarlo se cierran todas las sesiones abiertas de la cuenta.
    """
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes   = [AuthThrottle]
    throttle_scope     = "auth_login"

    def post(self, request):
        ser = PasswordResetConfirmSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        invalid = Response({
            "error": "El enlace de recuperación es inválido o expiró. Solicita uno nuevo."
        }, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.filter(email__iexact=d["email"], is_active=True).first()
        if user is None or not user.is_reset_token_valid(d["token"]):
            log_security_event("password_reset_invalid_token", request)
            return invalid

        errors = _password_errors(d["new_password"], user)
        if errors:
            return Response({"new_password": errors}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(d["new_password"])
        user.save(update_fields=["password"])
        user.clear_reset_token()
        revoked = revoke_refresh_tokens(user)

        AuditLog.log(
            action=AuditLog.Action.UPDATE,
            resource="auth",
            resource_id=str(user.pk),
            user=user,
            ip=client_ip(request),
            detail={"event": "password_reset", "sessions_revoked": revoked},
        )
        return Response({"message": "Contraseña restablecida exitosamente."})


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
            description="Par JWT, o desafío de 2FA si la cuenta lo tiene activo. Con la "
                        "cabecera X-Sentryx-Client: web el refresh va en una cookie HttpOnly."),
        401: OpenApiResponse(description="Correo o contraseña incorrectos."),
        403: OpenApiResponse(description="Correo sin verificar (solo con la contraseña correcta)."),
        429: OpenApiResponse(description="Cuenta o IP bloqueada por django-axes o límite de peticiones."),
    },
    examples=[
        OpenApiExample("Credenciales", request_only=True,
                       value={"email": "analista@sentryx.local", "password": "••••••••••"}),
        OpenApiExample("Sin 2FA", response_only=True,
                       value={"access": "eyJhbGciOi…", "refresh": "eyJhbGciOi…"}),
        OpenApiExample("Con 2FA", response_only=True,
                       value={"mfa_required": True, "mfa_token": "eyJ1aWQiOi…", "expires_in": 300}),
    ],
)
class ShieldTokenObtainPairView(TokenObtainPairView):
    """
    Login JWT.

    Con 2FA activo no entrega JWT: responde {"mfa_required": true,
    "mfa_token": ...} y el cliente debe llamar a /auth/mfa/verify/.
    Con MFA_REQUIRED_FOR_ADMINS=True, un admin sin 2FA recibe tokens con el
    claim mfa_setup_required que solo sirven para configurarlo.
    """
    serializer_class = ShieldTokenObtainPairSerializer
    authentication_classes = []
    throttle_classes = [AuthThrottle]
    throttle_scope   = "auth_login"

    def post(self, request, *args, **kwargs):
        email = str(request.data.get("email") or request.data.get("username") or "").strip()

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
        ip = client_ip(request)

        # Solo después de comprobar la contraseña: antes, este 403 revelaba qué
        # correos tienen cuenta a cualquiera que probara una contraseña falsa.
        if not user.is_email_verified:
            return Response({
                "error": "Debes verificar tu correo antes de iniciar sesión.",
                "code":  "email_not_verified",
            }, status=status.HTTP_403_FORBIDDEN)

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
            return cookies.token_response(request, body)
        return cookies.token_response(request, serializer.validated_data)


@extend_schema(
    tags=["auth"], summary="Renovar el access token",
    request=inline_serializer("RefreshRequest", {"refresh": serializers.CharField(required=False)}),
    responses={200: inline_serializer("RefreshResponse", {
        "access": serializers.CharField(), "refresh": serializers.CharField(required=False)}),
        401: OpenApiResponse(description="Refresh inválido, caducado o revocado.")},
    description="El panel web envía X-Sentryx-Client: web y el refresh va en la cookie "
                "HttpOnly; la extensión lo envía en el cuerpo.",
)
class ShieldTokenRefreshView(APIView):
    permission_classes     = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes       = [AuthThrottle]
    throttle_scope         = "auth_refresh"

    def post(self, request):
        refresh = request.data.get("refresh") if isinstance(request.data, dict) else None
        from_cookie = False
        if not refresh:
            # La cookie solo vale con la cabecera del panel: un formulario de
            # otro sitio no puede añadirla (CSRF), y SameSite=Strict tampoco
            # deja que el navegador envíe la cookie desde otro sitio.
            if not cookies.is_web_client(request):
                return Response({"detail": "Falta el refresh token.", "code": "token_not_valid"},
                                status=status.HTTP_401_UNAUTHORIZED)
            refresh = cookies.refresh_from_cookie(request)
            from_cookie = True

        ser = TokenRefreshSerializer(data={"refresh": refresh or ""})
        try:
            ser.is_valid(raise_exception=True)
        except (TokenError, serializers.ValidationError):
            log_security_event("refresh_rejected", request, level=logging.INFO)
            response = Response({"detail": "La sesión expiró. Inicia sesión de nuevo.",
                                 "code": "token_not_valid"}, status=status.HTTP_401_UNAUTHORIZED)
            return cookies.clear_refresh_cookie(response) if from_cookie else response
        return cookies.token_response(request, ser.validated_data)


@extend_schema(tags=["auth"], summary="Cerrar sesión (revoca el refresh token)",
               request=inline_serializer("LogoutRequest", {
                   "refresh": serializers.CharField(required=False)}),
               responses={205: None})
class LogoutView(APIView):
    """
    POST /api/v1/auth/logout/ — pone el refresh token en la lista negra y borra la
    cookie. Funciona aunque el access token ya haya caducado.
    """
    permission_classes     = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes       = [AuthThrottle]
    throttle_scope         = "auth_refresh"

    def post(self, request):
        refresh = request.data.get("refresh") if isinstance(request.data, dict) else None
        if not refresh and cookies.is_web_client(request):
            refresh = cookies.refresh_from_cookie(request)
        if refresh:
            try:
                token = RefreshToken(refresh)
                token.blacklist()
                user = User.objects.filter(pk=token.get("user_id")).first()
                AuditLog.log(AuditLog.Action.LOGOUT, "auth", user=user, ip=client_ip(request),
                             resource_id=str(user.pk) if user else "")
            except TokenError:
                pass  # Ya caducado o revocado: el resultado es el mismo
        return cookies.clear_refresh_cookie(Response(status=status.HTTP_205_RESET_CONTENT))


@extend_schema(tags=["auth"])
class UserMeView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/v1/auth/me/"""
    serializer_class   = UserMeSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names  = ["get", "patch", "head", "options"]

    def get_object(self):
        return self.request.user


@extend_schema(tags=["auth"])
class UserListView(generics.ListAPIView):
    """
    GET /api/v1/auth/users/ — usuarios de la organización del admin.
    Un admin de una empresa no ve las cuentas de las demás.
    """
    serializer_class   = UserListSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return User.objects.none()
        user = self.request.user
        qs = User.objects.all().order_by("-created_at")
        if user.is_superuser:
            return qs
        organization = org_of(user)
        if not organization:
            return qs.filter(pk=user.pk)
        return qs.filter(organization=organization)
