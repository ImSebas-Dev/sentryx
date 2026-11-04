"""Las pruebas corren sobre SQLite en memoria, sin depender de PostgreSQL."""
import os

os.environ["COMMUNITY_HUB_DATABASE_URL"] = "sqlite://"
os.environ["COMMUNITY_HUB_OPERATOR_KEY"] = "operator-test-key"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    settings.k_anonymity = 2
    settings.daily_limit = 1000
    settings.max_pending_nodes = 100
    with TestClient(app) as test_client:
        yield test_client
