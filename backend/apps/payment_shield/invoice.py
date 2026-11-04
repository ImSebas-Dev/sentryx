"""
Sentryx v2 — Lectura segura de la factura electrónica DIAN (UBL 2.1).

El XML y el ZIP llegan de un atacante potencial: no cambies defusedxml por otro
parser y no extraigas nada a disco. Este módulo no hace ninguna llamada de red:
el CUFE se valida solo en formato y el usuario lo consulta a mano en la DIAN.
"""
import io
import re
import zipfile
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from xml.etree.ElementTree import ParseError

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring

NS = {
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
}

# Ajusta estos límites si la DIAN cambia el contenido típico del ZIP (PDF + XML)
MAX_ZIP_ENTRIES       = 20
MAX_ZIP_TOTAL_BYTES   = 20 * 1024 * 1024
MAX_XML_BYTES         = 10 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200

NIT_WEIGHTS = (3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71)
CUFE_RE     = re.compile(r"^[0-9a-fA-F]{96}$")

# Enlace para que el usuario consulte a mano. No lo llames desde el backend.
DIAN_CATALOG_URL = "https://catalogo-vpfe.dian.gov.co/document/searchqr?documentkey={cufe}"


class InvoiceBlocked(Exception):
    """Adjunto rechazado por seguridad o ilegible. message se muestra al usuario."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class InvoiceData:
    nit: str = ""
    dv: str = ""
    cufe: str = ""
    payable_amount: Decimal | None = None
    currency: str = ""
    issue_date: str = ""
    account: str = ""  # Número completo: úsalo para comparar y no lo persistas nunca


def compute_nit_dv(nit: str) -> str:
    """Calcula el dígito de verificación con el módulo 11 de la DIAN."""
    digits = [int(d) for d in reversed(nit)]
    total  = sum(d * w for d, w in zip(digits, NIT_WEIGHTS))
    rest   = total % 11
    return str(rest if rest < 2 else 11 - rest)


def is_valid_nit(nit: str, dv: str) -> bool:
    nit, dv = (nit or "").strip(), (dv or "").strip()
    if not (nit.isdigit() and dv.isdigit() and len(dv) == 1 and 5 <= len(nit) <= 15):
        return False
    return compute_nit_dv(nit) == dv


def is_valid_cufe(cufe: str) -> bool:
    return bool(CUFE_RE.match(cufe or ""))


def dian_url(cufe: str) -> str:
    # Genera el enlace solo con un CUFE válido: el valor viene del adjunto
    return DIAN_CATALOG_URL.format(cufe=cufe) if is_valid_cufe(cufe) else ""


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_xml(raw: bytes):
    if len(raw) > MAX_XML_BYTES:
        raise InvoiceBlocked("xml_too_large", "El XML de la factura es demasiado grande.")
    try:
        # forbid_dtd bloquea XXE y expansión de entidades (billion laughs)
        return fromstring(raw, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except DefusedXmlException:
        raise InvoiceBlocked(
            "xml_forbidden",
            "El XML trae construcciones peligrosas (DTD o entidades) y se bloqueó.")
    except (ParseError, ValueError):
        raise InvoiceBlocked("xml_invalid", "El XML de la factura no se puede leer.")


def _text(node, path: str) -> str:
    found = node.find(path, NS)
    return (found.text or "").strip() if found is not None else ""


def _invoice_from_tree(root) -> InvoiceData:
    company = root.find(".//cac:AccountingSupplierParty//cbc:CompanyID", NS)
    amount_node = root.find("cac:LegalMonetaryTotal/cbc:PayableAmount", NS)
    data = InvoiceData(
        nit=re.sub(r"\D", "", company.text or "") if company is not None else "",
        dv=(company.get("schemeID") or "").strip() if company is not None else "",
        cufe=_text(root, "cbc:UUID"),
        issue_date=_text(root, "cbc:IssueDate"),
        account=re.sub(r"\D", "", _text(
            root, "cac:PaymentMeans/cac:PayeeFinancialAccount/cbc:ID")),
    )
    if amount_node is not None:
        data.currency = amount_node.get("currencyID") or ""
        try:
            data.payable_amount = Decimal((amount_node.text or "").strip())
        except InvalidOperation:
            data.payable_amount = None
    return data


def parse_invoice_xml(raw: bytes) -> InvoiceData | None:
    """
    Devuelve los datos de un Invoice directo o de un AttachedDocument (Invoice
    embebido en CDATA). Devuelve None si el XML es válido pero no es una factura.
    """
    root = _parse_xml(raw)
    name = _local_name(root.tag)
    if name == "Invoice":
        return _invoice_from_tree(root)
    if name != "AttachedDocument":
        return None

    # Pasa también el contenido del CDATA por el parser seguro: es otro XML sin confianza
    for desc in root.iterfind(".//cac:Attachment/cac:ExternalReference/cbc:Description", NS):
        content = (desc.text or "").strip()
        if "Invoice" not in content[:4096]:
            continue
        inner = _parse_xml(content.encode("utf-8"))
        if _local_name(inner.tag) == "Invoice":
            return _invoice_from_tree(inner)
    return None


def xml_documents_from_zip(raw: bytes) -> list[bytes]:
    """Lee los .xml del ZIP en memoria con límites contra zip bombs."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise InvoiceBlocked("zip_invalid", "El ZIP no se puede leer.")

    with archive:
        entries = archive.infolist()
        if len(entries) > MAX_ZIP_ENTRIES:
            raise InvoiceBlocked("zip_too_many_files", "El ZIP trae demasiados archivos.")
        # El tamaño declarado es solo un primer filtro: se puede falsificar
        declared = sum(e.file_size for e in entries)
        if declared > MAX_ZIP_TOTAL_BYTES:
            raise InvoiceBlocked("zip_bomb", "El ZIP descomprimido supera el límite permitido.")
        if raw and declared / len(raw) > MAX_COMPRESSION_RATIO:
            raise InvoiceBlocked("zip_bomb", "El ZIP tiene una compresión anormal y se bloqueó.")

        documents, consumed = [], 0
        for entry in entries:
            if entry.is_dir() or not entry.filename.lower().endswith(".xml"):
                continue
            if entry.flag_bits & 0x1:
                raise InvoiceBlocked("zip_encrypted", "El ZIP está protegido con contraseña.")
            try:
                with archive.open(entry) as handle:
                    # Lee con tope para no confiar en el tamaño declarado
                    content = handle.read(MAX_XML_BYTES + 1)
            except (zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError):
                raise InvoiceBlocked("zip_invalid", "El ZIP está dañado.")
            consumed += len(content)
            if len(content) > MAX_XML_BYTES or consumed > MAX_ZIP_TOTAL_BYTES:
                raise InvoiceBlocked("zip_bomb", "El ZIP descomprimido supera el límite permitido.")
            documents.append(content)
        return documents


def read_invoice(filename: str, raw: bytes) -> InvoiceData | None:
    """Devuelve la primera factura del adjunto, o None si el adjunto no trae ninguna."""
    lower = (filename or "").lower()
    documents = xml_documents_from_zip(raw) if lower.endswith(".zip") else [raw]
    for document in documents:
        invoice = parse_invoice_xml(document)
        if invoice is not None:
            return invoice
    return None


def zip_is_encrypted(raw: bytes) -> bool:
    """Indica si algún archivo del ZIP pide contraseña (lo usa Cuatro ojos)."""
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            return any(e.flag_bits & 0x1 for e in archive.infolist())
    except zipfile.BadZipFile:
        return False
