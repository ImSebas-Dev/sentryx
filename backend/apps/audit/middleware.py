"""Sentryx v2 — Middleware de auditoría automática."""
from django.utils.deprecation import MiddlewareMixin


class AuditLogMiddleware(MiddlewareMixin):
    WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
    SKIP_PATHS    = {"/api/v1/auth/token/", "/api/v1/health/", "/admin/jsi18n/"}
    # Los endpoints de 2FA registran sus propios eventos con más detalle
    SKIP_PREFIXES = ("/api/v1/auth/mfa/",)

    def process_response(self, request, response):
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
        resource    = parts[2] if len(parts) > 2 else "unknown"
        resource_id = parts[3] if len(parts) > 3 else ""
        ip = (request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
              or request.META.get("REMOTE_ADDR", ""))
        user = request.user if request.user.is_authenticated else None

        try:
            AuditLog.log(
                action=action_map[request.method], resource=resource,
                resource_id=resource_id, user=user, ip=ip,
                detail={"status_code": response.status_code, "path": request.path},
            )
        except Exception:
            pass

        return response
