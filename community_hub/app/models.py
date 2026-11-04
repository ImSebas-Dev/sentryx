"""
Modelos del hub. No agregues aquí columnas con contenido de correos, remitentes ni
nombres de usuarios: el hub solo debe poder ver hashes y datos agregados.
"""
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _now():
    return datetime.now(timezone.utc)


def _uuid():
    return str(uuid.uuid4())


class Node(Base):
    __tablename__ = "nodes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    # Lo ve solo el operador: nunca lo incluyas en una respuesta para los nodos
    name: Mapped[str] = mapped_column(String(120))
    sector: Mapped[str] = mapped_column(String(1))
    region: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending|active|suspended
    # Solo el hash: si se filtra la base, las keys siguen sin servir
    key_hash: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    registration_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    established: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    reports: Mapped[list["Report"]] = relationship(back_populates="node",
                                                   cascade="all, delete-orphan")


class Report(Base):
    """Un nodo reporta un indicador una sola vez; las repeticiones actualizan la fecha."""
    __tablename__ = "reports"
    __table_args__ = (UniqueConstraint("node_id", "ioc_hash", name="uniq_node_ioc"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), index=True)
    ioc_hash: Mapped[str] = mapped_column(String(64), index=True)
    ioc_type: Mapped[str] = mapped_column(String(10))
    phishing_type: Mapped[str] = mapped_column(String(10))
    mitre_technique: Mapped[str] = mapped_column(String(20))
    severity: Mapped[str] = mapped_column(String(10))
    sector: Mapped[str] = mapped_column(String(1))
    region: Mapped[str] = mapped_column(String(60))
    first_observed: Mapped[date] = mapped_column(Date)
    last_observed: Mapped[date] = mapped_column(Date, index=True)

    node: Mapped[Node] = relationship(back_populates="reports")


class DailyCount(Base):
    __tablename__ = "daily_counts"

    node_id: Mapped[str] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"),
                                         primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
