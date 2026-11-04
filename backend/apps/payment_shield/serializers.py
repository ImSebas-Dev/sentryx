"""Sentryx v2 — Serializers del Escudo de pagos."""
import re

from rest_framework import serializers

from apps.payment_shield import services
from apps.payment_shield.invoice import is_valid_nit
from apps.payment_shield.models import PaymentCheck, Supplier

DOMAIN_RE = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}$")


class SupplierSerializer(serializers.ModelSerializer):
    # Recibe el número una sola vez: se convierte en last4 + HMAC y no se devuelve nunca
    account_number = serializers.CharField(
        write_only=True, required=False, allow_blank=True, max_length=40,
        help_text="Número completo; no se guarda ni se devuelve")
    account_masked = serializers.SerializerMethodField()
    has_account    = serializers.SerializerMethodField()

    class Meta:
        model  = Supplier
        fields = ["id", "name", "nit", "dv", "email_domains", "contact_phone", "bank_name",
                  "account_number", "account_last4", "account_masked", "has_account",
                  "created_at", "updated_at"]
        read_only_fields = ["id", "account_last4", "created_at", "updated_at"]

    def get_account_masked(self, obj) -> str:
        return f"****{obj.account_last4}" if obj.account_last4 else ""

    def get_has_account(self, obj) -> bool:
        return bool(obj.account_hmac)

    def validate_nit(self, value):
        value = re.sub(r"[\s.-]", "", value)
        if not value.isdigit() or not 5 <= len(value) <= 15:
            raise serializers.ValidationError("El NIT debe tener solo dígitos (sin el DV).")
        return value

    def validate_email_domains(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Envía una lista de dominios.")
        cleaned = []
        for domain in value:
            domain = str(domain).strip().lower().lstrip("@")
            if not DOMAIN_RE.match(domain):
                raise serializers.ValidationError(f"Dominio inválido: {domain}")
            cleaned.append(domain)
        return sorted(set(cleaned))

    def validate_account_number(self, value):
        digits = re.sub(r"[\s-]", "", value or "")
        if not digits:
            return ""
        if not digits.isdigit() or not 9 <= len(digits) <= 20:
            raise serializers.ValidationError("La cuenta debe tener entre 9 y 20 dígitos.")
        if not services.is_configured():
            raise serializers.ValidationError(
                "No se puede registrar la cuenta: falta PAYMENT_SHIELD_SECRET en el servidor.")
        return digits

    def validate(self, attrs):
        nit = attrs.get("nit", getattr(self.instance, "nit", ""))
        dv  = attrs.get("dv", getattr(self.instance, "dv", ""))
        if not is_valid_nit(nit, dv):
            raise serializers.ValidationError(
                {"dv": "El dígito de verificación no corresponde al NIT."})
        organization = self.context["organization"]
        duplicates = Supplier.objects.filter(organization=organization, nit=nit)
        if self.instance:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError({"nit": "Ya hay un proveedor con ese NIT."})
        return attrs

    def _apply_account(self, validated):
        number = validated.pop("account_number", "")
        if number:
            validated["account_last4"] = number[-4:]
            validated["account_hmac"]  = services.account_hmac(number)

    def create(self, validated):
        self._apply_account(validated)
        return Supplier.objects.create(**validated)

    def update(self, instance, validated):
        self._apply_account(validated)
        return super().update(instance, validated)


class PaymentCheckSerializer(serializers.ModelSerializer):
    supplier = serializers.SerializerMethodField()
    verdict_label = serializers.CharField(source="get_verdict_display", read_only=True)
    risky = serializers.BooleanField(source="is_risky", read_only=True)
    message = serializers.SerializerMethodField()
    verified_by_name = serializers.CharField(source="verified_by.username", default=None,
                                             read_only=True)

    class Meta:
        model  = PaymentCheck
        fields = ["id", "alert", "organization", "intent_detected", "matched_keywords",
                  "extracted_banks", "extracted_account_last4", "supplier", "sender_domain",
                  "verdict", "verdict_label", "risky", "message", "invoice_data",
                  "invoice_checks", "status", "verified_by_name", "verified_at",
                  "verification_notes", "created_at"]
        read_only_fields = fields

    def get_supplier(self, obj) -> dict | None:
        return services.supplier_summary(obj.supplier)

    def get_message(self, obj) -> str:
        return services.VERDICT_MESSAGES[obj.verdict]


class VerifyCheckSerializer(serializers.Serializer):
    result = serializers.ChoiceField(choices=[
        PaymentCheck.Status.CALLED, PaymentCheck.Status.REJECTED, PaymentCheck.Status.APPROVED,
    ])
    notes = serializers.CharField(required=False, allow_blank=True, max_length=2000, default="")
