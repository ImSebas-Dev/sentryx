"""Pruebas del Escudo de pagos: reglas, factura DIAN, seguridad y endpoints."""
import io
import json
import zipfile
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.alerts.models import Alert
from apps.audit.models import AuditLog
from apps.payment_shield import invoice as invoice_lib
from apps.payment_shield import services
from apps.payment_shield.models import PaymentCheck, Supplier
from tests.utils import make_user

ML_PATCH = "apps.alerts.views.analyze_email_sync"
ORG = "Acme SAS"
FULL_ACCOUNT = "12345678901"
CUFE = "a" * 96
NIT, DV = "890903938", "8"  # Bancolombia: NIT público, sirve de ejemplo válido

ML_LOW = {
    "risk_score": 12.0, "classification": "legitimate", "phishing_type": "legitimate",
    "mitre_technique": "T1566", "mitre_tactic": "Initial Access",
    "scores_by_layer": {"headers": 10.0, "content": 12.0, "urls": 0.0},
    "features_by_layer": {}, "url_count": 0, "urls_analyzed": [],
}


def invoice_xml(nit=NIT, dv=DV, cufe=CUFE, amount="1500000.00", account=FULL_ACCOUNT):
    payment = (f"<cac:PaymentMeans><cac:PayeeFinancialAccount><cbc:ID>{account}</cbc:ID>"
               "</cac:PayeeFinancialAccount></cac:PaymentMeans>") if account else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
  xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
  xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:UUID schemeName="CUFE-SHA384">{cufe}</cbc:UUID>
  <cbc:IssueDate>2026-10-01</cbc:IssueDate>
  <cac:AccountingSupplierParty><cac:Party><cac:PartyTaxScheme>
    <cbc:CompanyID schemeID="{dv}" schemeName="31">{nit}</cbc:CompanyID>
  </cac:PartyTaxScheme></cac:Party></cac:AccountingSupplierParty>
  {payment}
  <cac:LegalMonetaryTotal>
    <cbc:PayableAmount currencyID="COP">{amount}</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>
</Invoice>"""


def attached_document(inner):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<AttachedDocument xmlns="urn:oasis:names:specification:ubl:schema:xsd:AttachedDocument-2"
  xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
  xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cac:Attachment><cac:ExternalReference>
    <cbc:Description><![CDATA[{inner}]]></cbc:Description>
  </cac:ExternalReference></cac:Attachment>
</AttachedDocument>"""


def make_zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buf.getvalue()


def make_supplier(organization=ORG, **extra):
    fields = dict(name="Proveedor Uno", nit=NIT, dv=DV, email_domains=["proveedor.co"],
                  contact_phone="6015550100", bank_name="Bancolombia",
                  account_last4=FULL_ACCOUNT[-4:], account_hmac=services.account_hmac(FULL_ACCOUNT))
    fields.update(extra)
    return Supplier.objects.create(organization=organization, **fields)


class TestNitDv(TestCase):

    def test_valid_nits(self):
        # NIT públicos de entidades colombianas
        for nit, dv in (("890903938", "8"), ("800197268", "4"), ("899999068", "1")):
            self.assertTrue(invoice_lib.is_valid_nit(nit, dv), nit)

    def test_invalid_nits(self):
        for nit, dv in (("890903938", "7"), ("800197268", "0"), ("abc", "1"), ("890903938", ""),
                        ("890903938", "12"), ("", "1")):
            self.assertFalse(invoice_lib.is_valid_nit(nit, dv), f"{nit}-{dv}")

    def test_cufe_format(self):
        self.assertTrue(invoice_lib.is_valid_cufe("F" * 96))
        self.assertFalse(invoice_lib.is_valid_cufe("a" * 95))
        self.assertFalse(invoice_lib.is_valid_cufe("g" * 96))

    def test_dian_link_only_for_valid_cufe(self):
        self.assertIn(CUFE, invoice_lib.dian_url(CUFE))
        self.assertEqual(invoice_lib.dian_url('"><script>'), "")


class TestIntent(TestCase):

    def test_detects_with_accents_and_uppercase(self):
        self.assertIn("certificacion bancaria",
                      services.detect_payment_intent("Adjunto CERTIFICACIÓN BANCARIA"))
        self.assertIn("evitar suspension",
                      services.detect_payment_intent("Pague para evitar suspensión del servicio"))
        self.assertIn("nueva cuenta", services.detect_payment_intent("Tenemos NUEVA CUENTA."))

    def test_ignores_normal_mail(self):
        self.assertEqual(services.detect_payment_intent("Nos vemos el lunes en la reunión."), [])


class TestAccountExtraction(TestCase):

    def test_extracts_with_separators_and_hides_number(self):
        found = services.extract_accounts("Consignar a la cuenta 123-456789-01 de ahorros")
        self.assertEqual(found[0]["last4"], "8901")
        self.assertEqual(found[0]["hmac"], services.account_hmac("12345678901"))
        self.assertNotIn("12345678901", json.dumps(found))

    def test_spaces_are_accepted(self):
        self.assertEqual(services.extract_accounts("cuenta 1234 5678 9012")[0]["last4"], "9012")

    def test_ignores_nit_phone_and_dates(self):
        text = "NIT 900123456. Celular 3001234567. Fecha 2026-11-04. Factura 123456789."
        self.assertEqual(services.extract_accounts(text), [])

    def test_nequi_counts_as_account(self):
        self.assertEqual(services.extract_accounts("Paga por Nequi 3001234567")[0]["last4"], "4567")

    def test_length_limits(self):
        self.assertEqual(services.extract_accounts("cuenta 12345678"), [])
        self.assertEqual(services.extract_accounts("cuenta " + "1" * 21), [])

    def test_banks_are_detected_without_accents(self):
        banks = services.extract_banks("Pagar en banco de bogota o en ITAU")
        self.assertEqual(sorted(banks), ["Banco de Bogotá", "Itaú"])

    @override_settings(PAYMENT_SHIELD_EXTRA_BANKS=["Banco Nuevo"])
    def test_bank_list_is_configurable(self):
        self.assertEqual(services.extract_banks("en Banco Nuevo"), ["Banco Nuevo"])


class TestLookalike(TestCase):

    def test_detects_lookalikes(self):
        for fake in ("proveedor.com", "proveedr.co", "pr0veedor.co", "proveedor.co.evil.tk",
                     "provee.dor.co"):
            self.assertTrue(services.is_lookalike(fake, "proveedor.co"), fake)
        self.assertTrue(services.is_lookalike("rnicrosoft.com", "microsoft.com"))
        self.assertTrue(services.is_lookalike("paypa1.com", "paypal.com"))

    def test_two_level_colombian_suffix(self):
        for fake in ("transandes.co", "transandes.com", "transandez.com.co",
                     "pagos.transandes.net", "transandes.evil.tk", "tr4nsandes.com.co"):
            self.assertTrue(services.is_lookalike(fake, "transandes.com.co"), fake)
        self.assertFalse(services.is_lookalike("otraempresa.com.co", "transandes.com.co"))

    def test_cyrillic_homoglyph(self):
        self.assertTrue(services.is_lookalike("prоveedor.co", "proveedor.co"))

    def test_unrelated_domains_are_not_lookalikes(self):
        self.assertFalse(services.is_lookalike("empresa-x.org", "proveedor.co"))
        self.assertFalse(services.is_lookalike("proveedor.co", "proveedor.co"))
        # Nombres cortos: dos ediciones no alcanzan para considerarlo imitación
        self.assertFalse(services.is_lookalike("xy.co", "ab.co"))

    def test_sender_uses_real_address_not_display_name(self):
        self.assertEqual(
            services.domain_from_header('"pagos@proveedor.co" <x@evil.tk>'), "evil.tk")


class TestInvoiceParsing(TestCase):

    def test_direct_invoice(self):
        data = invoice_lib.parse_invoice_xml(invoice_xml().encode())
        self.assertEqual((data.nit, data.dv, data.cufe), (NIT, DV, CUFE))
        self.assertEqual(str(data.payable_amount), "1500000.00")
        self.assertEqual(data.issue_date, "2026-10-01")
        self.assertEqual(data.account, FULL_ACCOUNT)

    def test_attached_document(self):
        inner = invoice_xml().replace('<?xml version="1.0" encoding="UTF-8"?>', "")
        data = invoice_lib.parse_invoice_xml(attached_document(inner).encode())
        self.assertEqual(data.nit, NIT)

    def test_other_xml_is_not_an_invoice(self):
        self.assertIsNone(invoice_lib.parse_invoice_xml(b"<notes><a>1</a></notes>"))

    def test_invoice_inside_zip(self):
        raw = make_zip({"factura.pdf": b"%PDF", "ad0001.xml": invoice_xml()})
        self.assertEqual(invoice_lib.read_invoice("factura.zip", raw).nit, NIT)

    def test_xxe_is_blocked(self):
        xxe = (b'<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
               b"<Invoice>&xxe;</Invoice>")
        with self.assertRaises(invoice_lib.InvoiceBlocked) as ctx:
            invoice_lib.parse_invoice_xml(xxe)
        self.assertEqual(ctx.exception.code, "xml_forbidden")

    def test_xxe_inside_cdata_is_blocked(self):
        inner = '<!DOCTYPE foo [<!ENTITY x SYSTEM "file:///etc/passwd">]><Invoice>&x;</Invoice>'
        with self.assertRaises(invoice_lib.InvoiceBlocked):
            invoice_lib.parse_invoice_xml(attached_document(inner).encode())

    def test_billion_laughs_is_blocked(self):
        bomb = (b'<!DOCTYPE lolz [<!ENTITY a "aaaaaaaa"><!ENTITY b "&a;&a;&a;&a;">]>'
                b"<Invoice>&b;</Invoice>")
        with self.assertRaises(invoice_lib.InvoiceBlocked):
            invoice_lib.parse_invoice_xml(bomb)

    def test_zip_bomb_is_blocked(self):
        raw = make_zip({"bomba.xml": b"0" * (30 * 1024 * 1024)})
        with self.assertRaises(invoice_lib.InvoiceBlocked) as ctx:
            invoice_lib.read_invoice("factura.zip", raw)
        self.assertEqual(ctx.exception.code, "zip_bomb")

    def test_zip_high_ratio_is_blocked(self):
        raw = make_zip({"bomba.xml": b"0" * (5 * 1024 * 1024)})
        with self.assertRaises(invoice_lib.InvoiceBlocked):
            invoice_lib.read_invoice("factura.zip", raw)

    def test_zip_with_too_many_files_is_blocked(self):
        raw = make_zip({f"f{i}.xml": b"<a/>" for i in range(invoice_lib.MAX_ZIP_ENTRIES + 1)})
        with self.assertRaises(invoice_lib.InvoiceBlocked) as ctx:
            invoice_lib.read_invoice("factura.zip", raw)
        self.assertEqual(ctx.exception.code, "zip_too_many_files")


class TestVerdicts(TestCase):

    def setUp(self):
        self.supplier = make_supplier()

    def verdict(self, sender, body, attachments=()):
        return services.evaluate_email(ORG, sender, body, "", attachments)

    def upload(self, content, name="factura.xml"):
        return SimpleUploadedFile(name, content.encode() if isinstance(content, str) else content)

    def test_match(self):
        result = self.verdict("pagos@proveedor.co", f"Consignar a la cuenta {FULL_ACCOUNT}")
        self.assertEqual(result.verdict, PaymentCheck.Verdict.MATCH)
        self.assertFalse(result.is_risky)

    def test_subdomain_is_authorized(self):
        result = self.verdict("a@pagos.proveedor.co", "Pago pendiente")
        self.assertEqual(result.verdict, PaymentCheck.Verdict.MATCH)

    def test_account_mismatch(self):
        result = self.verdict("pagos@proveedor.co", "Nueva cuenta 99988877766 de ahorros")
        self.assertEqual(result.verdict, PaymentCheck.Verdict.ACCOUNT_MISMATCH)
        self.assertTrue(result.is_risky)

    def test_supplier_without_account_cannot_validate_new_one(self):
        Supplier.objects.filter(pk=self.supplier.pk).update(account_hmac="", account_last4="")
        result = self.verdict("pagos@proveedor.co", "Nueva cuenta 99988877766 de ahorros")
        self.assertEqual(result.verdict, PaymentCheck.Verdict.ACCOUNT_MISMATCH)

    def test_lookalike(self):
        result = self.verdict("pagos@proveedor.com", "Pago pendiente")
        self.assertEqual(result.verdict, PaymentCheck.Verdict.LOOKALIKE_DOMAIN)
        self.assertEqual(result.supplier, self.supplier)

    def test_display_name_cannot_impersonate_authorized_domain(self):
        result = self.verdict('"pagos@proveedor.co" <x@atacante.org>', "Pago pendiente")
        self.assertEqual(result.verdict, PaymentCheck.Verdict.UNKNOWN_SUPPLIER)

    def test_unknown_supplier(self):
        result = self.verdict("alguien@otra-empresa.org", "Pago pendiente")
        self.assertEqual(result.verdict, PaymentCheck.Verdict.UNKNOWN_SUPPLIER)

    def test_domain_mismatch_when_found_by_invoice_nit(self):
        result = self.verdict("alguien@otra-empresa.org", "Pago pendiente",
                              [self.upload(invoice_xml())])
        self.assertEqual(result.verdict, PaymentCheck.Verdict.DOMAIN_MISMATCH)

    def test_valid_invoice_matches(self):
        result = self.verdict("pagos@proveedor.co", "Adjunto factura por $ 1.500.000",
                              [self.upload(invoice_xml())])
        self.assertEqual(result.verdict, PaymentCheck.Verdict.MATCH)
        self.assertTrue(result.intent_detected)
        self.assertEqual(result.invoice_data["account_last4"], FULL_ACCOUNT[-4:])
        self.assertIn(CUFE, result.invoice_data["dian_url"])

    def test_invoice_checks_fail_individually(self):
        cases = [
            (dict(dv="1"), "nit_dv"),
            (dict(cufe="corto"), "cufe"),
            (dict(nit="800197268", dv="4"), "nit_supplier"),
        ]
        for kwargs, key in cases:
            result = self.verdict("pagos@proveedor.co", "Factura",
                                  [self.upload(invoice_xml(**kwargs))])
            self.assertEqual(result.verdict, PaymentCheck.Verdict.INVOICE_INCONSISTENT, key)
            failed = [c["key"] for c in result.checks if c["status"] == "fail"]
            self.assertIn(key, failed)

    def test_invoice_amount_differs_from_mail(self):
        result = self.verdict("pagos@proveedor.co", "El valor es $ 2.000.000",
                              [self.upload(invoice_xml())])
        self.assertEqual(result.verdict, PaymentCheck.Verdict.INVOICE_INCONSISTENT)

    def test_invoice_account_differs(self):
        result = self.verdict("pagos@proveedor.co", "Factura",
                              [self.upload(invoice_xml(account="99988877766"))])
        self.assertEqual(result.verdict, PaymentCheck.Verdict.ACCOUNT_MISMATCH)

    def test_blocked_attachment_makes_invoice_inconsistent(self):
        xxe = '<!DOCTYPE a [<!ENTITY x SYSTEM "file:///etc/passwd">]><Invoice>&x;</Invoice>'
        result = self.verdict("pagos@proveedor.co", "Pago pendiente", [self.upload(xxe)])
        self.assertEqual(result.verdict, PaymentCheck.Verdict.INVOICE_INCONSISTENT)

    @override_settings(PAYMENT_SHIELD_MAX_ATTACHMENT_MB=1)
    def test_oversized_attachment_is_not_read(self):
        big = self.upload(b"0" * (1024 * 1024 + 1))
        with patch.object(invoice_lib, "read_invoice") as read:
            result = self.verdict("pagos@proveedor.co", "Factura", [big])
        read.assert_not_called()
        self.assertTrue(any(c["key"] == "attachment" and c["status"] == "fail"
                            for c in result.checks))

    @override_settings(PAYMENT_SHIELD_SECRET="")
    def test_without_secret_comparison_is_disabled_not_broken(self):
        result = self.verdict("pagos@proveedor.co", "Nueva cuenta 99988877766 de ahorros")
        account = next(c for c in result.checks if c["key"] == "account")
        self.assertEqual(account["status"], "na")
        self.assertEqual(result.verdict, PaymentCheck.Verdict.MATCH)


class ShieldApiCase(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.admin = make_user("admin@acme.co", role="admin", organization=ORG)
        self.analyst = make_user("ana@acme.co", organization=ORG)
        self.viewer = make_user("ver@acme.co", role="viewer", organization=ORG)
        self.other_admin = make_user("gerente@otra.co", role="admin", organization="Otra SAS")


class TestSupplierApi(ShieldApiCase):
    URL = "/api/v1/payment-shield/suppliers/"

    def payload(self, **extra):
        return {"name": "Proveedor Uno", "nit": NIT, "dv": DV,
                "email_domains": ["Proveedor.co"], "contact_phone": "6015550100",
                "bank_name": "Bancolombia", "account_number": "123-456789-01", **extra}

    def test_admin_creates_and_account_never_returns(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(self.URL, self.payload(), format="json")
        self.assertEqual(resp.status_code, 201, resp.data)
        supplier = Supplier.objects.get()
        self.assertEqual(supplier.organization, ORG)
        self.assertEqual(supplier.account_last4, "8901")
        self.assertEqual(supplier.email_domains, ["proveedor.co"])
        self.assertEqual(supplier.account_hmac, services.account_hmac(FULL_ACCOUNT))
        for body in (resp, self.client.get(self.URL), self.client.get(f"{self.URL}{supplier.pk}/")):
            raw = body.content.decode()
            self.assertNotIn(FULL_ACCOUNT, raw)
            self.assertNotIn(supplier.account_hmac, raw)
            self.assertNotIn("account_hmac", raw)

    def test_account_number_is_not_stored_in_any_column_or_audit(self):
        self.client.force_authenticate(self.admin)
        self.client.post(self.URL, self.payload(), format="json")
        supplier = Supplier.objects.values().get()
        self.assertNotIn(FULL_ACCOUNT, json.dumps(supplier, default=str))
        for log in AuditLog.objects.all():
            self.assertNotIn(FULL_ACCOUNT, json.dumps(log.detail))

    def test_invalid_dv_is_rejected(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(self.URL, self.payload(dv="1"), format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("dv", resp.data)

    def test_duplicate_nit_same_org_rejected_other_org_allowed(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post(self.URL, self.payload(), format="json").status_code, 201)
        self.assertEqual(self.client.post(self.URL, self.payload(), format="json").status_code, 400)
        self.client.force_authenticate(self.other_admin)
        self.assertEqual(self.client.post(self.URL, self.payload(), format="json").status_code, 201)

    def test_analyst_reads_only_viewer_nothing(self):
        supplier = make_supplier()
        self.client.force_authenticate(self.analyst)
        self.assertEqual(self.client.get(self.URL).data["count"], 1)
        self.assertEqual(self.client.post(self.URL, self.payload(), format="json").status_code, 403)
        self.assertEqual(self.client.delete(f"{self.URL}{supplier.pk}/").status_code, 403)
        self.client.force_authenticate(self.viewer)
        self.assertEqual(self.client.get(self.URL).status_code, 403)

    def test_organization_isolation(self):
        supplier = make_supplier()
        self.client.force_authenticate(self.other_admin)
        self.assertEqual(self.client.get(self.URL).data["count"], 0)
        self.assertEqual(self.client.get(f"{self.URL}{supplier.pk}/").status_code, 404)
        self.assertEqual(self.client.delete(f"{self.URL}{supplier.pk}/").status_code, 404)
        self.assertTrue(Supplier.objects.filter(pk=supplier.pk).exists())

    def test_user_without_org_cannot_create_or_see(self):
        make_supplier(organization=ORG)
        loner = make_user("solo@x.co", role="admin")
        self.client.force_authenticate(loner)
        self.assertEqual(self.client.get(self.URL).data["count"], 0)
        self.assertEqual(self.client.post(self.URL, self.payload(), format="json").status_code, 400)

    def test_edit_without_account_keeps_it(self):
        supplier = make_supplier()
        self.client.force_authenticate(self.admin)
        resp = self.client.patch(f"{self.URL}{supplier.pk}/", {"contact_phone": "123"},
                                 format="json")
        self.assertEqual(resp.status_code, 200, resp.data)
        supplier.refresh_from_db()
        self.assertEqual(supplier.contact_phone, "123")
        self.assertTrue(supplier.account_hmac)

    def test_crud_is_audited(self):
        self.client.force_authenticate(self.admin)
        pk = self.client.post(self.URL, self.payload(), format="json").data["id"]
        self.client.delete(f"{self.URL}{pk}/")
        actions = set(AuditLog.objects.values_list("action", flat=True))
        self.assertLessEqual({"SUPPLIER_CREATED", "SUPPLIER_DELETED"}, actions)

    @override_settings(PAYMENT_SHIELD_SECRET="")
    def test_account_rejected_without_secret_but_supplier_works(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post(self.URL, self.payload(), format="json").status_code, 400)
        payload = self.payload()
        del payload["account_number"]
        self.assertEqual(self.client.post(self.URL, payload, format="json").status_code, 201)


class TestAnalyzeIntegration(ShieldApiCase):
    URL = "/api/v1/alerts/analyze/"

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.analyst)
        make_supplier()

    def analyze(self, sender, body, **extra):
        return self.client.post(self.URL, {
            "headers": {"from_addr": sender, "subject": "Pago"}, "body_text": body, **extra,
        }, format="json")

    @patch(ML_PATCH, return_value=ML_LOW)
    def test_risky_payment_forces_alert_without_touching_score(self, _):
        resp = self.analyze("pagos@proveedor.com", "Actualizamos nuestros datos bancarios")
        self.assertEqual(resp.status_code, 201, resp.data)
        alert = Alert.objects.get(pk=resp.data["alert_id"])
        self.assertEqual(alert.risk_score, 12.0)
        self.assertEqual(alert.severity, "HIGH")
        self.assertEqual(alert.phishing_type, "bec")
        self.assertEqual(alert.mitre_technique, "T1566.002")
        self.assertEqual(resp.data["risk_score"], 12.0)
        self.assertEqual(resp.data["classification"], "legitimate")
        signal = alert.risk_signals["payment_shield"]
        self.assertEqual(signal["verdict"], "lookalike_domain")
        self.assertEqual(signal["supplier"]["contact_phone"], "6015550100")
        self.assertEqual(alert.risk_signals["severity_adjustments"][0]["from"], "LOW")

    @patch(ML_PATCH, return_value={**ML_LOW, "risk_score": 90.0, "classification": "critical",
                                   "phishing_type": "spear"})
    def test_critical_is_never_lowered(self, _):
        resp = self.analyze("pagos@proveedor.com", "Nueva cuenta")
        alert = Alert.objects.get(pk=resp.data["alert_id"])
        self.assertEqual(alert.severity, "CRITICAL")
        self.assertEqual(alert.risk_score, 90.0)

    @patch(ML_PATCH, return_value=ML_LOW)
    def test_match_does_not_create_alert(self, _):
        resp = self.analyze("pagos@proveedor.co", f"Consignar a la cuenta {FULL_ACCOUNT}")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data["alert_created"])
        self.assertEqual(resp.data["payment_shield"]["verdict"], "match")
        self.assertEqual(Alert.objects.count(), 0)
        self.assertEqual(PaymentCheck.objects.count(), 1)

    @patch(ML_PATCH, return_value=ML_LOW)
    def test_no_intent_no_check(self, _):
        resp = self.analyze("x@y.co", "Nos vemos el lunes")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("payment_shield", resp.data)
        self.assertEqual(PaymentCheck.objects.count(), 0)

    @patch(ML_PATCH, return_value=ML_LOW)
    def test_account_number_never_in_response_alert_or_check(self, _):
        number = "99988877766"
        resp = self.analyze("pagos@proveedor.co", f"Nueva cuenta {number} de ahorros")
        raw = resp.content.decode()
        self.assertNotIn(number, raw)
        alert = Alert.objects.get(pk=resp.data["alert_id"])
        self.assertNotIn(number, json.dumps(alert.risk_signals))
        check = PaymentCheck.objects.get()
        self.assertEqual(check.extracted_account_last4, ["7766"])
        self.assertNotIn(number, json.dumps(check.invoice_checks))
        detail = self.client.get(f"/api/v1/alerts/{alert.pk}/").content.decode()
        self.assertNotIn(number, detail)
        self.assertIn("risk_signals", json.loads(detail))

    @patch(ML_PATCH, return_value=ML_LOW)
    def test_multipart_with_invoice(self, mock_ml):
        upload = SimpleUploadedFile("factura.xml", invoice_xml().encode())
        resp = self.client.post(self.URL, {
            "headers.from_addr": "pagos@proveedor.co", "headers.subject": "Factura",
            "body_text": "Adjunto factura por $ 1.500.000", "attachments": [upload],
        }, format="multipart")
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["payment_shield"]["verdict"], "match")
        self.assertEqual(resp.data["payment_shield"]["invoice"]["nit"], NIT)
        self.assertEqual(mock_ml.call_args[0][0]["headers"]["from"], "pagos@proveedor.co")

    @patch(ML_PATCH, return_value=ML_LOW)
    def test_xxe_through_endpoint_is_reported_not_500(self, _):
        xxe = b'<!DOCTYPE a [<!ENTITY x SYSTEM "file:///etc/passwd">]><Invoice>&x;</Invoice>'
        resp = self.client.post(self.URL, {
            "headers.from_addr": "pagos@proveedor.co", "body_text": "Pago pendiente",
            "attachments": [SimpleUploadedFile("f.xml", xxe)],
        }, format="multipart")
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data["payment_shield"]["verdict"], "invoice_inconsistent")
        self.assertNotIn("root:", resp.content.decode())

    @patch(ML_PATCH, return_value=ML_LOW)
    def test_shield_failure_does_not_break_analysis(self, _):
        with patch("apps.alerts.risk_layers.payment_shield.evaluate_email",
                   side_effect=RuntimeError("boom")):
            resp = self.analyze("a@b.co", "Pago pendiente")
        self.assertEqual(resp.status_code, 200)

    @patch(ML_PATCH, return_value=ML_LOW)
    def test_other_org_suppliers_are_not_used(self, _):
        self.client.force_authenticate(self.other_admin)
        resp = self.analyze("pagos@proveedor.co", "Pago pendiente")
        self.assertEqual(resp.data["payment_shield"]["verdict"], "unknown_supplier")
        self.assertIsNone(resp.data["payment_shield"]["supplier"])


class TestCheckEndpoints(ShieldApiCase):

    def make_check(self, organization=ORG, **extra):
        return PaymentCheck.objects.create(
            organization=organization, owner=self.analyst, intent_detected=True,
            verdict=PaymentCheck.Verdict.UNKNOWN_SUPPLIER, **extra)

    def url(self, check, suffix=""):
        return f"/api/v1/payment-shield/checks/{check.pk}/{suffix}"

    def test_list_and_detail_by_org(self):
        check = self.make_check()
        foreign = self.make_check(organization="Otra SAS")
        self.client.force_authenticate(self.admin)
        ids = [c["id"] for c in self.client.get("/api/v1/payment-shield/checks/").data["results"]]
        self.assertEqual(ids, [str(check.pk)])
        self.assertEqual(self.client.get(self.url(check)).status_code, 200)
        self.assertEqual(self.client.get(self.url(foreign)).status_code, 404)

    def test_viewer_is_rejected(self):
        check = self.make_check()
        self.client.force_authenticate(self.viewer)
        self.assertEqual(self.client.get(self.url(check)).status_code, 403)

    def test_verify_saves_who_when_and_audits(self):
        check = self.make_check()
        self.client.force_authenticate(self.analyst)
        resp = self.client.post(self.url(check, "verify/"),
                                {"result": "verified_by_call", "notes": "Confirmado"}, format="json")
        self.assertEqual(resp.status_code, 200, resp.data)
        check.refresh_from_db()
        self.assertEqual(check.status, "verified_by_call")
        self.assertEqual(check.verified_by, self.analyst)
        self.assertIsNotNone(check.verified_at)
        self.assertTrue(AuditLog.objects.filter(action="PAYMENT_VERIFIED",
                                                resource_id=str(check.pk)).exists())

    def test_verify_invalid_result(self):
        check = self.make_check()
        self.client.force_authenticate(self.analyst)
        resp = self.client.post(self.url(check, "verify/"), {"result": "x"}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_closed_check_cannot_be_reopened(self):
        check = self.make_check(status=PaymentCheck.Status.REJECTED)
        self.client.force_authenticate(self.analyst)
        resp = self.client.post(self.url(check, "verify/"),
                                {"result": "verified_by_call"}, format="json")
        self.assertEqual(resp.status_code, 409)

    def test_cannot_verify_foreign_check(self):
        check = self.make_check(organization="Otra SAS")
        self.client.force_authenticate(self.analyst)
        resp = self.client.post(self.url(check, "verify/"),
                                {"result": "rejected"}, format="json")
        self.assertEqual(resp.status_code, 404)

    def test_acknowledge_risk_is_audited(self):
        check = self.make_check()
        self.client.force_authenticate(self.analyst)
        self.assertEqual(self.client.post(self.url(check, "acknowledge-risk/")).status_code, 200)
        self.assertTrue(AuditLog.objects.filter(action="PAYMENT_RISK_ACK").exists())


class TestTenantBoundary(TestCase):

    def test_user_cannot_change_own_organization(self):
        user = make_user("hop@x.co", organization=ORG)
        client = APIClient()
        client.force_authenticate(user)
        client.patch("/api/v1/auth/me/", {"organization": "Otra SAS"}, format="json")
        user.refresh_from_db()
        self.assertEqual(user.organization, ORG)
