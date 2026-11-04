"""Sentryx v2 — Endpoints de la Red de alerta (/api/v1/community/)."""
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.models import AuditLog
from apps.community import services
from apps.community.serializers import (
    CommunitySettingsSerializer, EnableSerializer, SummarySerializer, UpdateSerializer,
)
from apps.users.organization import org_of
from apps.users.permissions import IsAdminUser

TAG = "Red de alerta"
NO_ORG = {"error": "Tu usuario no tiene organización: pide que te la asignen."}


def client_ip(request):
    return (request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
            or request.META.get("REMOTE_ADDR", ""))


def _audit(request, action, community, **detail):
    AuditLog.log(action=action, resource="community.settings", resource_id=str(community.pk),
                 user=request.user, ip=client_ip(request), detail=detail)


class SettingsView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(tags=[TAG], summary="Estado de la red y texto de consentimiento (solo admin)",
                   responses={200: CommunitySettingsSerializer,
                              400: OpenApiResponse(description="El usuario no tiene organización.")})
    def get(self, request):
        community = services.settings_for(org_of(request.user))
        if community is None:
            return Response(NO_ORG, status=status.HTTP_400_BAD_REQUEST)
        return Response(CommunitySettingsSerializer(community).data)

    @extend_schema(tags=[TAG], summary="Cambiar sector y departamento (solo admin)",
                   request=UpdateSerializer, responses={200: CommunitySettingsSerializer})
    def put(self, request):
        community = services.settings_for(org_of(request.user))
        if community is None:
            return Response(NO_ORG, status=status.HTTP_400_BAD_REQUEST)
        ser = UpdateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        community.sector = ser.validated_data["sector"]
        community.region = ser.validated_data["region"]
        community.save(update_fields=["sector", "region"])
        _audit(request, AuditLog.Action.CONFIG_CHANGE, community,
               sector=community.sector, region=community.region)
        return Response(CommunitySettingsSerializer(community).data)


class EnableView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(tags=[TAG], summary="Activar la red aceptando el consentimiento (solo admin)",
                   request=EnableSerializer, responses={200: CommunitySettingsSerializer})
    def post(self, request):
        community = services.settings_for(org_of(request.user))
        if community is None:
            return Response(NO_ORG, status=status.HTTP_400_BAD_REQUEST)
        ser = EnableSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        services.enable(community, request.user, ser.validated_data["sector"],
                        ser.validated_data["region"])
        _audit(request, AuditLog.Action.COMMUNITY_OPT_IN, community,
               consent_version=community.consent_version,
               sector=community.sector, region=community.region)
        return Response(CommunitySettingsSerializer(community).data)


class DisableView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(tags=[TAG], summary="Desactivar la red y pedir el borrado de los aportes",
                   request=None, responses={200: CommunitySettingsSerializer})
    def post(self, request):
        community = services.settings_for(org_of(request.user))
        if community is None:
            return Response(NO_ORG, status=status.HTTP_400_BAD_REQUEST)
        deleted = services.disable(community)
        _audit(request, AuditLog.Action.COMMUNITY_OPT_OUT, community, hub_deleted=deleted)
        return Response(CommunitySettingsSerializer(community).data)


class SyncNowView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(tags=[TAG], summary="Sincronizar ahora con el hub (solo admin)", request=None,
                   responses={200: inline_serializer("CommunitySyncResult", {
                       "result": serializers.DictField()})})
    def post(self, request):
        return Response({"result": services.sync()})


class SummaryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=[TAG], summary="Tarjeta del dashboard: campañas de tu sector y región",
                   responses={200: SummarySerializer})
    def get(self, request):
        return Response(services.summary(org_of(request.user)))
