"""Sentryx v2 — Serializers, views y URLs de Threat Intelligence."""
from rest_framework import serializers, generics, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import (
    extend_schema, inline_serializer, OpenApiExample, OpenApiParameter, OpenApiResponse,
)
from drf_spectacular.types import OpenApiTypes

from apps.threat_intel.models import IOC
from apps.users.permissions   import IsAnalystOrAbove


# ── Serializers ───────────────────────────────────────────
class IOCSerializer(serializers.ModelSerializer):
    class Meta:
        model  = IOC
        fields = ["id", "ioc_type", "value", "threat_level", "source",
                    "mitre_technique", "description", "tags",
                    "vt_detections", "vt_total", "brand_targeted",
                    "is_active", "first_seen", "last_seen"]
        read_only_fields = ["id", "first_seen", "last_seen",
                            "vt_detections", "vt_total"]


class IOCCreateSerializer(serializers.ModelSerializer):
    """Para añadir IOCs manuales desde el dashboard (RFC-023)."""
    class Meta:
        model  = IOC
        fields = ["ioc_type", "value", "threat_level", "mitre_technique",
                    "description", "tags", "brand_targeted"]


class IOCCheckSerializer(serializers.Serializer):
    """Consultar si un valor está en la lista negra de IOCs."""
    value    = serializers.CharField(max_length=512)
    ioc_type = serializers.ChoiceField(choices=IOC.IOCType.choices, required=False)


# ── Views ─────────────────────────────────────────────────
@extend_schema(tags=["threat-intel"])
class IOCListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/v1/threat-intel/iocs/   — lista IOCs
    POST /api/v1/threat-intel/iocs/   — añadir IOC manual
    """
    permission_classes = [IsAnalystOrAbove]
    queryset           = IOC.objects.filter(is_active=True).order_by("-last_seen")

    def get_serializer_class(self):
        return IOCCreateSerializer if self.request.method == "POST" else IOCSerializer

    def create(self, request, *args, **kwargs):
        ser = IOCCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ioc = ser.save(source=IOC.Source.MANUAL, is_active=True)
        return Response(IOCSerializer(ioc).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["threat-intel"], request=IOCCheckSerializer, responses={200: OpenApiTypes.OBJECT})
class IOCCheckView(APIView):
    """
    POST /api/v1/threat-intel/check/
    Consulta rápida: ¿está este valor en algún IOC activo?
    Usada por el motor de correlación y el dashboard.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        ser = IOCCheckSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        value = ser.validated_data["value"].lower()
        ioc_type = ser.validated_data.get("ioc_type")

        qs = IOC.objects.filter(is_active=True, value__iexact=value)
        if ioc_type:
            qs = qs.filter(ioc_type=ioc_type)

        match = qs.first()
        return Response({
            "found":         match is not None,
            "ioc_type":      match.ioc_type       if match else None,
            "threat_level":  match.threat_level    if match else None,
            "source":        match.source          if match else None,
            "mitre_technique":match.mitre_technique if match else None,
            "brand_targeted":match.brand_targeted  if match else None,
        })


@extend_schema(tags=["threat-intel"], responses={200: OpenApiTypes.OBJECT})
class ThreatIntelStatsView(APIView):
    """GET /api/v1/threat-intel/stats/ — resumen de IOCs por fuente."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from django.db.models import Count
        by_source = dict(
            IOC.objects.filter(is_active=True)
                        .values_list("source")
                        .annotate(c=Count("id"))
        )
        by_type = dict(
            IOC.objects.filter(is_active=True)
                        .values_list("ioc_type")
                        .annotate(c=Count("id"))
        )
        return Response({
            "total_active": IOC.objects.filter(is_active=True).count(),
            "by_source":    by_source,
            "by_type":      by_type,
        })
