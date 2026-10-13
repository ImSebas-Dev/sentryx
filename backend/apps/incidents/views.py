"""Sentryx v2 — Views de incidentes."""
import logging
from django.utils import timezone
from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiExample

from apps.incidents.models import Incident, IncidentTimeline
from apps.incidents.serializers import (
    IncidentListSerializer, IncidentDetailSerializer,
    IncidentCreateSerializer, IncidentUpdateSerializer,
)
from apps.audit.models     import AuditLog
from apps.users.permissions import IsAnalystOrAbove, IsAuthenticatedReadOnly

logger = logging.getLogger(__name__)


def incident_queryset(user):
    """
    Incidentes visibles con aislamiento por usuario: el admin ve todos; el
    resto, los que creó o tiene asignados. Usar siempre esta función (la
    reutilizan los informes) para que listado, detalle e informes coincidan.
    """
    from django.db.models import Q
    qs = Incident.objects.select_related("assigned_to", "created_by")
    if getattr(user, "is_admin", False):
        return qs
    return qs.filter(Q(created_by=user) | Q(assigned_to=user))


@extend_schema(tags=["incidents"])
class IncidentListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/v1/incidents/  — lista de incidentes
    POST /api/v1/incidents/  — crear incidente (agrupa alertas)
    """
    permission_classes = [IsAuthenticatedReadOnly]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Incident.objects.none()
        return incident_queryset(self.request.user).prefetch_related("alerts") \
            .order_by("-created_at")

    def get_serializer_class(self):
        return IncidentCreateSerializer if self.request.method == "POST" \
                else IncidentListSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["request"] = self.request
        return ctx

    @extend_schema(responses={201: IncidentDetailSerializer}, examples=[
        OpenApiExample("Incidente BEC", request_only=True, value={
            "title": "Campaña BEC contra tesorería", "severity": "HIGH",
            "description": "Tres correos con cambio de cuenta bancaria.",
            "alert_ids": ["3fa85f64-5717-4562-b3fc-2c963f66afa6"]}),
    ])
    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        incident = ser.save()

        # Registro en auditoría
        ip = (request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
                or request.META.get("REMOTE_ADDR", ""))
        AuditLog.log(AuditLog.Action.CREATE, "incidents",
                        user=request.user, resource_id=str(incident.pk), ip=ip)

        # Primer evento en timeline
        IncidentTimeline.objects.create(
            incident=incident,
            event_type="created",
            description=f"Incidente creado por {request.user.username}.",
            actor=request.user,
        )

        return Response(IncidentDetailSerializer(incident).data,
                        status=status.HTTP_201_CREATED)


@extend_schema(tags=["incidents"])
class IncidentDetailView(generics.RetrieveUpdateAPIView):
    """
    GET   /api/v1/incidents/<uuid>/  — detalle con timeline y alertas
    PATCH /api/v1/incidents/<uuid>/  — cambiar status / reasignar
    """
    permission_classes = [IsAuthenticatedReadOnly]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Incident.objects.none()
        return incident_queryset(self.request.user) \
            .prefetch_related("alerts", "timeline__actor")

    def get_serializer_class(self):
        return IncidentUpdateSerializer if self.request.method == "PATCH" \
                else IncidentDetailSerializer

    def partial_update(self, request, *args, **kwargs):
        incident   = self.get_object()
        old_status = incident.status
        response   = super().partial_update(request, *args, **kwargs)
        incident.refresh_from_db()

        # Si el estado cambia, registrar en timeline y auditoría
        if "status" in request.data and request.data["status"] != old_status:
            new_status = request.data["status"]

            IncidentTimeline.objects.create(
                incident=incident,
                event_type="status_change",
                description=f"Estado cambiado de '{old_status}' a '{new_status}'.",
                actor=request.user,
            )

            # Marcar fecha de cierre
            if new_status == "closed":
                Incident.objects.filter(pk=incident.pk).update(
                    closed_at=timezone.now()
                )

            ip = (request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
                    or request.META.get("REMOTE_ADDR", ""))
            AuditLog.log(AuditLog.Action.UPDATE, "incidents",
                            user=request.user, resource_id=str(incident.pk), ip=ip,
                            detail={"old_status": old_status, "new_status": new_status})

        return response
