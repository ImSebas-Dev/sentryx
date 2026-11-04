"""Conexión a la base de datos propia del hub."""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings

_options = {}
if settings.database_url.startswith("sqlite"):
    # Las pruebas usan SQLite en memoria: comparte una sola conexión entre hilos
    _options = {"connect_args": {"check_same_thread": False}, "poolclass": StaticPool}

engine = create_engine(settings.database_url, **_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
