"""
Sentryx v2 — Lógica del Escudo de pagos.

Esta capa de negocio corre DESPUÉS del ensemble y no toca risk_score ni los
modelos: solo produce un veredicto que eleva la severidad de la alerta y se
explica en Alert.risk_signals["payment_shield"].
"""
import hashlib
import hmac
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from email.utils import parseaddr
from html import unescape

from django.conf import settings

from apps.payment_shield import invoice as invoice_lib
from apps.payment_shield.models import PaymentCheck, Supplier

logger = logging.getLogger(__name__)

# Amplía aquí las frases de intención de pago. Escríbelas sin tildes y en
# minúsculas: el texto del correo se normaliza antes de comparar.
PAYMENT_INTENT_KEYWORDS = [
    "cambio de cuenta", "cambio de datos bancarios", "nueva cuenta", "cuenta nueva",
    "actualizamos nuestros datos bancarios", "actualizar datos bancarios",
    "actualizacion de datos bancarios", "nuevos datos bancarios", "datos bancarios",
    "consignar", "consignacion", "consigne", "transferir", "transferencia", "transfiera",
    "pago pendiente", "pagos pendientes", "realizar el pago", "realice el pago",
    "factura vencida", "facturas vencidas", "factura pendiente", "saldo pendiente",
    "certificacion bancaria", "evitar suspension", "evitar la suspension",
    "cuenta de cobro", "soporte de pago", "comprobante de pago",
]
# Patrones que una frase fija no cubre ("pague hoy", "cuenta de ahorros No. 123").
PAYMENT_INTENT_PATTERNS = [
    (r"\bpag(?:ar|ue|uen|o)\s+(?:hoy|inmediat\w+|urgente|ya)\b", "pago urgente"),
    (r"\bcuenta\s+(?:de\s+)?(?:ahorros?|corriente)\b", "cuenta de ahorros o corriente"),
]

# Agrega bancos sin tocar el código con PAYMENT_SHIELD_EXTRA_BANKS en el .env
COLOMBIAN_BANKS = [
    "Bancolombia", "Davivienda", "BBVA", "Banco de Bogotá", "Banco de Occidente",
    "Banco Popular", "AV Villas", "Banco Caja Social", "Scotiabank Colpatria", "Itaú",
    "Banco Agrario", "Bancoomeva", "Banco Falabella", "Banco Pichincha", "Nequi",
    "Daviplata", "Lulo Bank", "Nu Colombia",
]

# El número de cuenta admite guiones o espacios: 123-456789-01
ACCOUNT_RE = re.compile(r"(?<![\w.,/-])\d(?:[ -]?\d){8,19}(?![\w])")
DATE_LIKE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")
ACCOUNT_CONTEXT_RE = re.compile(
    r"cuenta|ahorros?|corriente|consign|transfer|nequi|daviplata|deposit|abon")
# Descarta los números precedidos por estas palabras: un NIT tiene 9 dígitos y un
# celular 10, y sin este filtro cada firma de correo sería una "cuenta distinta".
NON_ACCOUNT_CONTEXT_RE = re.compile(
    r"\bnit\b|\bc\.?c\.?\b|cedula|factura|cufe|\btel\b|telefono|\bcel\b|celular|movil"
    r"|whatsapp|radicado|referencia|\bref\b|orden|pedido|contrato|\bfax\b")
CELLPHONE_RE = re.compile(r"^3\d{9}$")
AMOUNT_RES = [
    re.compile(r"(?:\$|\bcop\b)\s*(\d[\d.,]*)"),
    re.compile(r"(\d[\d.,]*)\s*(?:\bcop\b|\bpesos\b)"),
]
TAG_RE = re.compile(r"<[^>]+>")

# Sustituciones visuales típicas de los dominios falsos. Amplía aquí las nuevas.
CONFUSABLE_SEQUENCES = [("rn", "m"), ("vv", "w"), ("0", "o"), ("1", "l"), ("5", "s")]
CONFUSABLE_CHARS = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x", "і": "i", "ѕ": "s",
})

VERDICT_MESSAGES = {
    PaymentCheck.Verdict.MATCH:
        "Los datos del correo coinciden con el proveedor registrado.",
    PaymentCheck.Verdict.ACCOUNT_MISMATCH:
        "La cuenta del correo no coincide con la registrada para este proveedor.",
    PaymentCheck.Verdict.DOMAIN_MISMATCH:
        "El correo viene de un dominio que este proveedor no tiene autorizado.",
    PaymentCheck.Verdict.LOOKALIKE_DOMAIN:
        "El dominio del remitente se parece al de un proveedor, pero no es el registrado.",
    PaymentCheck.Verdict.UNKNOWN_SUPPLIER:
        "El remitente no corresponde a ningún proveedor registrado.",
    PaymentCheck.Verdict.INVOICE_INCONSISTENT:
        "La factura adjunta tiene datos inconsistentes.",
}


# ── Normalización ─────────────────────────────────────────
def normalize_text(text: str) -> str:
    """Quita tildes, pasa a minúsculas y colapsa espacios."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", plain).lower().strip()


def email_text(body_text: str, body_html: str) -> str:
    return body_text or unescape(TAG_RE.sub(" ", body_html or ""))


def domain_from_header(from_header: str) -> str:
    """
    Toma el dominio de la dirección real, no del nombre visible. Un remitente como
    '"pagos@proveedor.co" <x@evil.tk>' debe dar evil.tk.
    """
    _, address = parseaddr(from_header or "")
    if "@" not in address:
        return ""
    return address.rsplit("@", 1)[1].strip().lower().rstrip(".")


# ── 1. Intención de pago ──────────────────────────────────
def detect_payment_intent(text: str) -> list[str]:
    normalized = normalize_text(text)
    found = [kw for kw in PAYMENT_INTENT_KEYWORDS if kw in normalized]
    found += [label for pattern, label in PAYMENT_INTENT_PATTERNS
              if re.search(pattern, normalized)]
    return found


# ── 2. Extracción ─────────────────────────────────────────
def is_configured() -> bool:
    return bool(settings.PAYMENT_SHIELD_SECRET)


def account_hmac(number: str) -> str:
    """HMAC del número sin separadores. Devuelve vacío si falta PAYMENT_SHIELD_SECRET."""
    digits = re.sub(r"\D", "", number or "")
    if not digits or not is_configured():
        return ""
    return hmac.new(settings.PAYMENT_SHIELD_SECRET.encode(), digits.encode(),
                    hashlib.sha256).hexdigest()


def _last_match_end(pattern, window: str) -> int:
    ends = [m.end() for m in pattern.finditer(window)]
    return ends[-1] if ends else -1


def extract_accounts(text: str) -> list[dict]:
    """
    Devuelve [{"last4", "hmac"}]. No devuelvas ni registres el número completo:
    fuera de esta función solo deben existir esos dos valores.
    """
    normalized = normalize_text(text)
    accounts, seen = [], set()
    for match in ACCOUNT_RE.finditer(normalized):
        raw = match.group(0)
        digits = re.sub(r"\D", "", raw)
        if not 9 <= len(digits) <= 20 or DATE_LIKE_RE.match(raw) or digits in seen:
            continue
        window = normalized[max(0, match.start() - 40):match.start()]
        account_at = _last_match_end(ACCOUNT_CONTEXT_RE, window)
        other_at   = _last_match_end(NON_ACCOUNT_CONTEXT_RE, window)
        # La palabra más cercana al número decide qué tipo de número es
        if other_at > account_at:
            continue
        if CELLPHONE_RE.match(digits) and account_at < 0:
            continue
        seen.add(digits)
        accounts.append({"last4": digits[-4:], "hmac": account_hmac(digits)})
    return accounts


def known_banks() -> list[str]:
    extra = [b.strip() for b in settings.PAYMENT_SHIELD_EXTRA_BANKS if b.strip()]
    return COLOMBIAN_BANKS + extra


def extract_banks(text: str) -> list[str]:
    normalized = normalize_text(text)
    return [bank for bank in known_banks()
            if re.search(rf"\b{re.escape(normalize_text(bank))}\b", normalized)]


def parse_amount(raw: str) -> Decimal | None:
    """Acepta 1.500.000,50 (Colombia), 1,500,000.50 y 1500000."""
    raw = raw.strip().rstrip(".,")
    decimal_part = ""
    last_sep = max(raw.rfind("."), raw.rfind(","))
    # Solo 1 o 2 dígitos tras el último separador son decimales; 3 son miles
    if last_sep >= 0 and len(raw) - last_sep - 1 in (1, 2):
        decimal_part = raw[last_sep + 1:]
        raw = raw[:last_sep]
    digits = re.sub(r"[.,]", "", raw)
    try:
        return Decimal(f"{digits}.{decimal_part or '0'}")
    except InvalidOperation:
        return None


def extract_amounts(text: str) -> list[Decimal]:
    normalized = normalize_text(text)
    found = []
    for pattern in AMOUNT_RES:
        for match in pattern.finditer(normalized):
            value = parse_amount(match.group(1))
            if value is not None:
                found.append(value)
    return found


# ── 3. Dominios ───────────────────────────────────────────
def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1,
                               previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def _canonical_domain(domain: str) -> str:
    domain = domain.translate(CONFUSABLE_CHARS)
    for seq, repl in CONFUSABLE_SEQUENCES:
        domain = domain.replace(seq, repl)
    return domain


def _decode_idn(domain: str) -> str:
    try:
        return domain.encode("ascii").decode("idna") if "xn--" in domain else domain
    except (UnicodeError, ValueError):
        return domain


def domain_is_authorized(sender: str, domains: list[str]) -> bool:
    """Acepta el dominio exacto o un subdominio suyo (pagos.proveedor.co)."""
    return any(sender == d or sender.endswith(f".{d}") for d in domains)


def is_lookalike(sender: str, registered: str) -> bool:
    """Indica si sender imita a registered sin ser el mismo dominio."""
    sender, registered = _decode_idn((sender or "").lower()), registered.lower()
    if not sender or sender == registered:
        return False
    # proveedor.co.evil.tk: el dominio legítimo aparece como prefijo de otro
    if sender.startswith(f"{registered}."):
        return True
    sender_sld, _, sender_tld = sender.rpartition(".")
    reg_sld, _, reg_tld = registered.rpartition(".")
    if sender_sld == reg_sld and sender_tld != reg_tld:
        return True
    if _canonical_domain(sender) == _canonical_domain(registered):
        return True
    # Con un nombre corto dos ediciones lo convierten en otro dominio cualquiera
    allowed = 2 if len(reg_sld) >= 5 else 1
    return levenshtein(sender, registered) <= allowed


# ── 4. Orquestación ───────────────────────────────────────
def _check(key: str, label: str, status: str, detail: str = "") -> dict:
    return {"key": key, "label": label, "status": status, "detail": detail}


@dataclass
class ShieldResult:
    organization: str
    sender_domain: str
    intent_detected: bool
    matched_keywords: list
    extracted_banks: list
    extracted_last4: list
    supplier: Supplier | None
    verdict: str
    invoice_data: dict = field(default_factory=dict)
    checks: list = field(default_factory=list)

    @property
    def is_risky(self) -> bool:
        return self.intent_detected and self.verdict != PaymentCheck.Verdict.MATCH

    @property
    def should_persist(self) -> bool:
        return self.intent_detected or bool(self.invoice_data) or any(
            c["key"] == "attachment" for c in self.checks)


def _find_supplier(suppliers, sender_domain, invoice_nit):
    """Devuelve (proveedor, estado_del_dominio): authorized | lookalike | mismatch | unknown."""
    for supplier in suppliers:
        if sender_domain and domain_is_authorized(sender_domain, supplier.email_domains):
            return supplier, "authorized"
    for supplier in suppliers:
        if any(is_lookalike(sender_domain, d) for d in supplier.email_domains):
            return supplier, "lookalike"
    if invoice_nit:
        for supplier in suppliers:
            if supplier.nit == invoice_nit:
                return supplier, "mismatch"
    return None, "unknown"


def _account_matches(supplier: Supplier, candidate_hmac: str) -> bool:
    return bool(candidate_hmac and supplier.account_hmac) and hmac.compare_digest(
        candidate_hmac, supplier.account_hmac)


def _read_attachments(attachments):
    """Devuelve (factura, checks). Un adjunto malo se reporta, no tumba el análisis."""
    max_bytes = settings.PAYMENT_SHIELD_MAX_ATTACHMENT_MB * 1024 * 1024
    found, checks = None, []
    for upload in attachments:
        name = (getattr(upload, "name", "") or "").lower()
        if not name.endswith((".xml", ".zip")):
            continue
        # Comprueba el tamaño antes de leer: read() cargaría todo a memoria
        if upload.size > max_bytes:
            checks.append(_check(
                "attachment", "Adjunto", "fail",
                f"Supera el límite de {settings.PAYMENT_SHIELD_MAX_ATTACHMENT_MB} MB."))
            continue
        upload.seek(0)
        raw = upload.read()
        upload.seek(0)
        try:
            invoice = invoice_lib.read_invoice(name, raw)
        except invoice_lib.InvoiceBlocked as exc:
            checks.append(_check("attachment", "Adjunto", "fail", exc.message))
            continue
        if invoice is not None and found is None:
            found = invoice
    return found, checks


def _invoice_checks(invoice, supplier, body_amounts) -> list[dict]:
    checks = [
        _check("nit_dv", "Dígito de verificación del NIT",
               "pass" if invoice_lib.is_valid_nit(invoice.nit, invoice.dv) else "fail",
               f"NIT {invoice.nit}-{invoice.dv}"),
        _check("cufe", "Formato del CUFE (96 hexadecimales)",
               "pass" if invoice_lib.is_valid_cufe(invoice.cufe) else "fail"),
    ]
    if supplier:
        checks.append(_check("nit_supplier", "El NIT corresponde al proveedor",
                             "pass" if invoice.nit == supplier.nit else "fail",
                             f"Registrado: {supplier.nit}-{supplier.dv}"))
    else:
        checks.append(_check("nit_supplier", "El NIT corresponde al proveedor", "na",
                             "No hay proveedor con qué comparar."))
    if invoice.payable_amount is None or not body_amounts:
        checks.append(_check("amount", "El valor coincide con el del correo", "na",
                             "El correo no menciona un valor."))
    else:
        # Tolera centavos: el correo suele redondear el total de la factura
        same = any(abs(a - invoice.payable_amount) < 1 for a in body_amounts)
        checks.append(_check("amount", "El valor coincide con el del correo",
                             "pass" if same else "fail",
                             f"Factura: {invoice.payable_amount}"))
    return checks


def _account_check(supplier, accounts) -> dict:
    label = "La cuenta coincide con la registrada"
    if not accounts:
        return _check("account", label, "na", "No se encontró número de cuenta.")
    if not supplier:
        return _check("account", label, "na", "No hay proveedor con qué comparar.")
    if not is_configured():
        return _check("account", label, "na",
                      "Comparación desactivada: falta PAYMENT_SHIELD_SECRET.")
    shown = ", ".join(f"****{a['last4']}" for a in accounts)
    if not supplier.account_hmac:
        return _check("account", label, "fail",
                      f"{shown}: el proveedor no tiene cuenta registrada para comparar.")
    if all(_account_matches(supplier, a["hmac"]) for a in accounts):
        return _check("account", label, "pass", shown)
    return _check("account", label, "fail",
                  f"{shown}; registrada: ****{supplier.account_last4}")


def evaluate_email(organization, from_header, body_text, body_html="", attachments=()):
    """Evalúa el correo sin escribir en la base de datos. Devuelve un ShieldResult."""
    text = email_text(body_text, body_html)
    sender_domain = domain_from_header(from_header)
    keywords = detect_payment_intent(text)
    suppliers = list(Supplier.objects.filter(organization=organization)) if organization else []

    invoice, checks = _read_attachments(attachments)
    supplier, domain_state = _find_supplier(
        suppliers, sender_domain, invoice.nit if invoice else "")

    if invoice is not None:
        keywords = keywords + ["factura electrónica adjunta"]
        checks += _invoice_checks(invoice, supplier, extract_amounts(text))

    accounts = extract_accounts(text)
    if supplier is not None:
        # Un NIT sin contexto "nit" también aparece en firmas: no lo trates como cuenta
        nit_hmac = account_hmac(supplier.nit)
        accounts = [a for a in accounts if not (nit_hmac and a["hmac"] == nit_hmac)]
    if invoice is not None and invoice.account:
        accounts.append({"last4": invoice.account[-4:],
                         "hmac": account_hmac(invoice.account)})
    account_check = _account_check(supplier, accounts)
    checks.append(account_check)

    domain_labels = {
        "authorized": ("pass", "Dominio autorizado"),
        "lookalike":  ("fail", "Se parece a un dominio registrado, pero no es el mismo"),
        "mismatch":   ("fail", "El proveedor no tiene autorizado este dominio"),
        "unknown":    ("na",   "No hay proveedor registrado con este dominio"),
    }
    status, detail = domain_labels[domain_state]
    checks.insert(0, _check("domain", "Dominio del remitente", status,
                            f"{sender_domain or 'sin dominio'}: {detail}"))

    if supplier is None:
        verdict = PaymentCheck.Verdict.UNKNOWN_SUPPLIER
    elif domain_state == "lookalike":
        verdict = PaymentCheck.Verdict.LOOKALIKE_DOMAIN
    elif domain_state == "mismatch":
        verdict = PaymentCheck.Verdict.DOMAIN_MISMATCH
    elif account_check["status"] == "fail":
        verdict = PaymentCheck.Verdict.ACCOUNT_MISMATCH
    elif any(c["status"] == "fail" for c in checks):
        verdict = PaymentCheck.Verdict.INVOICE_INCONSISTENT
    else:
        verdict = PaymentCheck.Verdict.MATCH

    invoice_data = {}
    if invoice is not None:
        invoice_data = {
            "nit": invoice.nit, "dv": invoice.dv, "cufe": invoice.cufe,
            "payable_amount": str(invoice.payable_amount)
                              if invoice.payable_amount is not None else "",
            "currency": invoice.currency, "issue_date": invoice.issue_date,
            # Conserva solo los últimos 4 dígitos de la cuenta de la factura
            "account_last4": invoice.account[-4:] if invoice.account else "",
            "dian_url": invoice_lib.dian_url(invoice.cufe),
        }

    return ShieldResult(
        organization=organization, sender_domain=sender_domain,
        intent_detected=bool(keywords), matched_keywords=keywords,
        extracted_banks=extract_banks(text),
        extracted_last4=[a["last4"] for a in accounts],
        supplier=supplier, verdict=verdict,
        invoice_data=invoice_data, checks=checks,
    )


def persist_check(result: ShieldResult, alert, owner) -> PaymentCheck:
    return PaymentCheck.objects.create(
        alert=alert, owner=owner, organization=result.organization,
        intent_detected=result.intent_detected,
        matched_keywords=result.matched_keywords,
        extracted_banks=result.extracted_banks,
        extracted_account_last4=result.extracted_last4,
        supplier=result.supplier, sender_domain=result.sender_domain,
        verdict=result.verdict, invoice_data=result.invoice_data,
        invoice_checks=result.checks,
    )


def supplier_summary(supplier: Supplier | None) -> dict | None:
    if supplier is None:
        return None
    return {
        "id": str(supplier.pk), "name": supplier.name,
        "nit": supplier.nit, "dv": supplier.dv,
        "contact_phone": supplier.contact_phone, "bank_name": supplier.bank_name,
        "account_last4": supplier.account_last4,
    }


def check_summary(check: PaymentCheck) -> dict:
    """Forma de risk_signals["payment_shield"]. No incluyas aquí ningún HMAC."""
    return {
        "check_id": str(check.pk),
        "intent_detected": check.intent_detected,
        "matched_keywords": check.matched_keywords,
        "verdict": check.verdict,
        "verdict_label": check.get_verdict_display(),
        "message": VERDICT_MESSAGES[check.verdict],
        "risky": check.is_risky,
        "sender_domain": check.sender_domain,
        "extracted_banks": check.extracted_banks,
        "extracted_account_last4": check.extracted_account_last4,
        "supplier": supplier_summary(check.supplier),
        "invoice": check.invoice_data,
        "checks": check.invoice_checks,
        "status": check.status,
    }
