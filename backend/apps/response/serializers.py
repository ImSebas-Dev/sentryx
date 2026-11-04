"""Sentryx v2 — Serializers de la respuesta guiada."""
import json
import re

from rest_framework import serializers

from apps.response.models import EmergencyContact, Playbook, ResponseSession

PHONE_RE = re.compile(r"^[+\d][\d\s()-]{4,29}$")
MAX_ANSWERS_BYTES = 4096


class PlaybookSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Playbook
        fields = ["key", "title", "description", "severity", "steps"]
        read_only_fields = fields


class EmergencyContactSerializer(serializers.ModelSerializer):
    is_placeholder = serializers.SerializerMethodField()

    class Meta:
        model  = EmergencyContact
        fields = ["id", "name", "phone", "url", "kind", "is_placeholder"]
        read_only_fields = ["id"]

    def get_is_placeholder(self, obj) -> bool:
        return not obj.phone and not obj.url

    def validate_phone(self, value):
        # Este valor termina en un enlace tel: de la interfaz
        if value and not PHONE_RE.match(value):
            raise serializers.ValidationError("Escribe un teléfono válido.")
        return value

    def validate_url(self, value):
        if value and not value.lower().startswith(("https://", "http://")):
            raise serializers.ValidationError("Usa una dirección http o https.")
        return value


class ResponseSessionSerializer(serializers.ModelSerializer):
    playbook = PlaybookSerializer(read_only=True)
    alert_id = serializers.UUIDField(read_only=True, allow_null=True)
    incident_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model  = ResponseSession
        fields = ["id", "playbook", "alert_id", "incident_id", "answers", "steps_state",
                  "started_at", "completed_at", "status"]
        read_only_fields = fields


class StartSessionSerializer(serializers.Serializer):
    playbook_key = serializers.SlugField()
    alert_id = serializers.UUIDField(required=False, allow_null=True)
    answers = serializers.DictField(required=False, default=dict)

    def validate_answers(self, value):
        if len(json.dumps(value)) > MAX_ANSWERS_BYTES:
            raise serializers.ValidationError("Las respuestas son demasiado largas.")
        return value


class StepSerializer(serializers.Serializer):
    done = serializers.BooleanField(default=True)
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000, default="")
