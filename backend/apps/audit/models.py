"""
Sentryx v2 — Log de auditoría inmutable (RFC-053, RNF-022).
Solo INSERT. Ningún usuario puede modificar ni borrar registros.
Cumple trazabilidad requerida por Ley 1581/2012.
"""
import hashlib
import uuid
from django.db import models
from django.conf import settings


class AuditLog(models.Model):
    class Action(models.TextChoices):
        LOGIN         = "LOGIN",         "Inicio de sesión"
        LOGOUT        = "LOGOUT",        "Cierre de sesión"
        LOGIN_FAILED  = "LOGIN_FAILED",  "Intento fallido"
        READ          = "READ",          "Consulta"
        CREATE        = "CREATE",        "Creación"
        UPDATE        = "UPDATE",        "Modificación"
        DELETE        = "DELETE",        "Eliminación"
        EXPORT        = "EXPORT",        "Exportación"
        ANALYZE       = "ANALYZE",       "Análisis de correo"
        CONFIG_CHANGE = "CONFIG_CHANGE", "Cambio de configuración"

    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    action      = models.CharField(max_length=20, choices=Action.choices)
    resource    = models.CharField(max_length=80)
    resource_id = models.CharField(max_length=40, blank=True)

    user              = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True,
        on_delete=models.SET_NULL, related_name="audit_logs",
    )
    username_snapshot = models.CharField(max_length=150)
    ip_hash           = models.CharField(max_length=64, blank=True,
                            help_text="SHA-256(IP + salt) — nunca la IP real")
    detail            = models.JSONField(default=dict, blank=True)
    occurred_at       = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        db_table = "audit_log"
        ordering = ["-occurred_at"]
        indexes  = [
            models.Index(fields=["user", "occurred_at"]),
            models.Index(fields=["resource", "resource_id"]),
            models.Index(fields=["occurred_at"]),
        ]

    def save(self, *args, **kwargs):
        if self.pk and AuditLog.objects.filter(pk=self.pk).exists():
            raise PermissionError("Los registros de auditoría son inmutables.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Los registros de auditoría no pueden eliminarse.")

    @classmethod
    def log(cls, action, resource, user=None, resource_id="", ip=None, detail=None,
            actor="anonymous"):
        """
        Registrar un evento. Pasar actor="system" en las tareas programadas
        para distinguirlas de peticiones anónimas.
        """
        salt    = settings.PSEUDONYMIZATION_SALT
        ip_hash = hashlib.sha256(f"{ip}{salt}".encode()).hexdigest() if ip else ""
        return cls.objects.create(
            action=action, resource=resource,
            resource_id=str(resource_id),
            user=user,
            username_snapshot=user.username if user else actor,
            ip_hash=ip_hash,
            detail=detail or {},
        )

    def __str__(self):
        return f"[{self.occurred_at:%Y-%m-%d %H:%M}] {self.action} — {self.username_snapshot}"
