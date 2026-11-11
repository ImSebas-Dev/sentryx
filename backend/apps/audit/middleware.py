"""Sentryx v2 — Middleware de auditoría automática y vigilancia de accesos."""
import logging

from django.utils.deprecation import MiddlewareMixin

from apps.audit.utils import client_ip, log_security_event

logger = logging.getLogger(__name__)

# Respuestas que indican sondeo o abuso: van al log de seguridad (no a la BD,
# para que un atacante no pueda llenar la tabla de auditoría con peticiones).
SUSPICIOUS_STATUS = {401: "unauthorized", 403: "forbidden", 429: "throttled"}


class AuditLogMiddleware(MiddlewareMixin):
    WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
    SKIP_PATHS    = {"/api/v1/auth/token/", "/api/v1/health/", "/admin/jsi18n/"}
    # Los endpoints de 2FA y de sesión registran sus propios eventos con más detalle
    SKIP_PREFIXES = ("/api/v1/auth/mfa/", "/api/v1/auth/token/", "/api/v1/auth/logout/")

    def process_response(self, request, response):
        if response.status_code in SUSPICIOUS_STATUS and request.path.startswith("/api/"):
            log_security_event(f"http_{SUSPICIOUS_STATUS[response.status_code]}", request,
                               level=logging.INFO, method=request.method,
                               status=response.status_code)

        if (request.method not in self.WRITE_METHODS
                or request.path in self.SKIP_PATHS
                or request.path.startswith(self.SKIP_PREFIXES)
                or not request.path.startswith("/api/")
                or response.status_code >= 500):
            return response

        from apps.audit.models import AuditLog

        action_map = {
            "POST": AuditLog.Action.CREATE,
            "PUT":  AuditLog.Action.UPDATE,
            "PATCH":AuditLog.Action.UPDATE,
            "DELETE":AuditLog.Action.DELETE,
        }
        parts       = [p for p in request.path.split("/") if p]
        resource    = parts[2][:80] if len(parts) > 2 else "unknown"
        resource_id = parts[3][:40] if len(parts) > 3 else ""
        user = request.user if getattr(request, "user", None) and request.user.is_authenticated else None

        try:
            AuditLog.log(
                action=action_map[request.method], resource=resource,
                resource_id=resource_id, user=user, ip=client_ip(request),
                detail={"status_code": response.status_code, "path": request.path[:200]},
            )
        except Exception:
            logger.exception("[Audit] No se pudo registrar la petición")

        return response
