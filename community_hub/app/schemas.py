"""
Esquemas de la API. extra="forbid" rechaza cualquier campo que no esté aquí: así un
nodo mal configurado no puede enviar por error un asunto, un remitente o un usuario.
"""
from datetime import date, timedelta

from pydantic import BaseModel, ConfigDict, Field, field_validator

SECTORS = set("ABCDEFGHIJKLMNOPQRSTU")
REGIONS = {
    "Amazonas", "Antioquia", "Arauca", "Atlántico", "Bogotá D.C.", "Bolívar", "Boyacá", "Caldas",
    "Caquetá", "Casanare", "Cauca", "Cesar", "Chocó", "Córdoba", "Cundinamarca", "Guainía",
    "Guaviare", "Huila", "La Guajira", "Magdalena", "Meta", "Nariño", "Norte de Santander",
    "Putumayo", "Quindío", "Risaralda", "San Andrés y Providencia", "Santander", "Sucre",
    "Tolima", "Valle del Cauca", "Vaupés", "Vichada",
}
PHISHING_TYPES = {"spear", "whaling", "bec", "clone", "vishing", "smishing", "generic", "unknown"}
MAX_REPORT_AGE_DAYS = 30


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _check_sector(value: str) -> str:
    if value not in SECTORS:
        raise ValueError("El sector debe ser una sección CIIU de la A a la U.")
    return value


def _check_region(value: str) -> str:
    if value not in REGIONS:
        raise ValueError("La región debe ser un departamento de Colombia o Bogotá D.C.")
    return value


class RegisterRequest(Strict):
    name: str = Field(min_length=2, max_length=120)
    sector: str
    region: str

    _sector = field_validator("sector")(_check_sector)
    _region = field_validator("region")(_check_region)


class RegisterResponse(BaseModel):
    node_id: str
    registration_token: str
    status: str


class ClaimRequest(Strict):
    node_id: str = Field(max_length=36)
    registration_token: str = Field(max_length=100)


class ClaimResponse(BaseModel):
    node_api_key: str


class Indicator(Strict):
    ioc_type: str = Field(pattern=r"^(domain|url)$")
    ioc_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    phishing_type: str
    mitre_technique: str = Field(pattern=r"^T1566(\.00[1-4])?$")
    severity: str = Field(pattern=r"^(LOW|MEDIUM|HIGH|CRITICAL)$")
    sector: str
    region: str
    observed_on: date

    _sector = field_validator("sector")(_check_sector)
    _region = field_validator("region")(_check_region)

    @field_validator("phishing_type")
    @classmethod
    def _check_type(cls, value):
        if value not in PHISHING_TYPES:
            raise ValueError("Tipo de phishing desconocido.")
        return value

    @field_validator("observed_on")
    @classmethod
    def _check_date(cls, value):
        today = date.today()
        if value > today + timedelta(days=1) or value < today - timedelta(days=MAX_REPORT_AGE_DAYS):
            raise ValueError("La fecha observada está fuera del rango permitido.")
        return value


class IndicatorBatch(Strict):
    indicators: list[Indicator] = Field(max_length=500)


class FeedItem(BaseModel):
    """No agregues aquí nada que identifique a un nodo: ni id, ni nombre, ni key."""
    ioc_hash: str
    ioc_type: str
    company_count: int
    sectors: list[str]
    regions: list[str]
    phishing_type: str
    mitre_technique: str
    first_seen: date
    last_seen: date


class Feed(BaseModel):
    indicators: list[FeedItem]
