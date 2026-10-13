"""
Sentryx v2 — Cliente del ML Engine.
Centraliza todas las llamadas HTTP al servicio FastAPI de análisis.
"""
import httpx
from django.conf import settings


class MLEngineError(Exception):
    pass


def _headers() -> dict:
    return {
        "X-API-Key":    settings.ML_ENGINE_API_KEY,
        "Content-Type": "application/json",
    }


async def analyze_email_async(email_payload: dict) -> dict:
    """
    Llama al endpoint /analyze/email del ML Engine de forma asíncrona.
    Timeout de 10s — el análisis debería completarse en < 3s.
    """
    url = f"{settings.ML_ENGINE_URL}/analyze/email"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=email_payload, headers=_headers())
            resp.raise_for_status()
            return resp.json()
    except httpx.TimeoutException:
        raise MLEngineError("ML Engine no respondió en 10 segundos.")
    except httpx.HTTPStatusError as e:
        raise MLEngineError(f"ML Engine retornó {e.response.status_code}: {e.response.text}")
    except httpx.ConnectError:
        raise MLEngineError("No se pudo conectar al ML Engine. ¿Está corriendo?")


def analyze_email_sync(email_payload: dict) -> dict:
    """
    Versión síncrona — usada desde tareas Celery.
    """
    url = f"{settings.ML_ENGINE_URL}/analyze/email"
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, json=email_payload, headers=_headers())
            resp.raise_for_status()
            return resp.json()
    except httpx.TimeoutException:
        raise MLEngineError("ML Engine no respondió en 10 segundos.")
    except httpx.HTTPStatusError as e:
        raise MLEngineError(f"ML Engine retornó {e.response.status_code}: {e.response.text}")
    except httpx.ConnectError:
        raise MLEngineError("No se pudo conectar al ML Engine.")
