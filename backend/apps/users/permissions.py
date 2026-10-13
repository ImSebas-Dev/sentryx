"""
Sentryx v2 — Permisos RBAC reutilizables.
Uso en cualquier view: permission_classes = [IsAnalystOrAbove]
"""
from rest_framework.permissions import BasePermission


class IsAdminUser(BasePermission):
    """Solo administradores."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.is_admin)


class IsAnalystOrAbove(BasePermission):
    """Analistas y administradores — pueden crear/modificar alertas e incidentes."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.is_analyst)


class IsAuthenticatedReadOnly(BasePermission):
    """Cualquier usuario autenticado puede leer; escritura solo analistas+."""
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return request.user.is_analyst


class IsAuthenticatedUnlessDebug(BasePermission):
    """
    Documentación OpenAPI: abierta en desarrollo (DEBUG=True), solo usuarios
    autenticados en producción. Se evalúa en cada petición, no al importar.
    """
    def has_permission(self, request, view):
        from django.conf import settings
        return bool(settings.DEBUG or (request.user and request.user.is_authenticated))
