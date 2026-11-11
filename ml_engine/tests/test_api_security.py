"""Sentryx v2 — Autenticación del motor ML (X-API-Key)."""
import importlib

import pytest
from fastapi.testclient import TestClient


def load_app(monkeypatch, key):
    monkeypatch.setenv("ML_ENGINE_API_KEY", key)
    import api.main as main
    return importlib.reload(main)


def test_without_configured_key_everything_is_refused(monkeypatch):
    main = load_app(monkeypatch, "")
    client = TestClient(main.app)
    # Antes, sin variable, la clave era "dev-key" y cualquiera podía reentrenar
    resp = client.post("/admin/reload", headers={"X-API-Key": "dev-key"})
    assert resp.status_code == 503


@pytest.mark.parametrize("header", [None, "incorrecta"])
def test_wrong_or_missing_key_is_rejected(monkeypatch, header):
    main = load_app(monkeypatch, "clave-larga-de-prueba")
    client = TestClient(main.app)
    headers = {"X-API-Key": header} if header else {}
    assert client.post("/admin/reload", headers=headers).status_code == 403


def test_docs_are_off_by_default(monkeypatch):
    monkeypatch.delenv("ML_ENABLE_DOCS", raising=False)
    main = load_app(monkeypatch, "clave-larga-de-prueba")
    client = TestClient(main.app)
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
