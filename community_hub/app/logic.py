"""
Reglas de la red: k-anonimato, antienvenenamiento y límites.

Decisiones que conviene mantener:
  - Un indicador solo sale al feed cuando la suma de pesos de sus nodos llega a K.
    Como cada peso es como máximo 1, eso también garantiza K nodos distintos.
  - La reputación se calcula al vuelo a partir de los reportes: no hay un número
    guardado que pueda quedar desactualizado.
"""
import hashlib
import secrets
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.models import DailyCount, Node, Report

# Un nodo nuevo cuenta como medio reporte durante este tiempo
PROBATION_DAYS = 7
NEW_NODE_WEIGHT = 0.5
# La reputación sube con los reportes que otro nodo confirmó y baja con los que nadie
# confirma. Lo normal es que muchos reportes sean únicos: por eso el castigo se activa
# solo por debajo de este umbral, típico de quien inventa indicadores.
LOW_REPUTATION = 0.2
LOW_REPUTATION_FACTOR = 0.25
REPUTATION_MIN_AGE_DAYS = 7
REPUTATION_PRIOR = 5


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def new_secret() -> str:
    return secrets.token_urlsafe(32)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(moment: datetime | None) -> datetime | None:
    # SQLite devuelve fechas sin zona; PostgreSQL las devuelve con zona
    if moment is not None and moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment


def find_node_by_key(db: Session, api_key: str) -> Node | None:
    if not api_key:
        return None
    return db.scalar(select(Node).where(Node.key_hash == hash_secret(api_key)))


def _recent_reports(db: Session) -> list[Report]:
    cutoff = date.today() - timedelta(days=settings.retention_days)
    return list(db.scalars(
        select(Report).options(joinedload(Report.node)).where(Report.last_observed >= cutoff)
    ).unique())


def compute_reputations(reports: list[Report], today: date | None = None) -> dict[str, float]:
    """Proporción de reportes de cada nodo que otro nodo confirmó, con un previo favorable."""
    today = today or date.today()
    by_ioc = defaultdict(set)
    for report in reports:
        by_ioc[report.ioc_hash].add(report.node_id)

    total, confirmed = Counter(), Counter()
    cutoff = today - timedelta(days=REPUTATION_MIN_AGE_DAYS)
    for report in reports:
        # Un reporte reciente aún no ha tenido tiempo de ser confirmado por nadie
        if report.first_observed > cutoff:
            continue
        total[report.node_id] += 1
        if len(by_ioc[report.ioc_hash]) > 1:
            confirmed[report.node_id] += 1
    return {node_id: (confirmed[node_id] + REPUTATION_PRIOR) / (count + REPUTATION_PRIOR)
            for node_id, count in total.items()}


def node_weight(node: Node, reputation: float = 1.0, now: datetime | None = None) -> float:
    now = now or utcnow()
    approved_at = _aware(node.approved_at)
    in_probation = (not node.established and approved_at is not None
                    and now - approved_at < timedelta(days=PROBATION_DAYS))
    weight = NEW_NODE_WEIGHT if in_probation else 1.0
    if reputation < LOW_REPUTATION:
        weight *= LOW_REPUTATION_FACTOR
    return weight


def build_feed(db: Session, since: date | None = None) -> list[dict]:
    reports = _recent_reports(db)
    reputations = compute_reputations(reports)
    grouped = defaultdict(list)
    for report in reports:
        # Un nodo suspendido deja de contar, aunque sus reportes sigan guardados
        if report.node.status == "active":
            grouped[report.ioc_hash].append(report)

    feed = []
    for ioc_hash, items in grouped.items():
        weight = sum(node_weight(r.node, reputations.get(r.node_id, 1.0)) for r in items)
        if weight < settings.k_anonymity:
            continue
        last_seen = max(r.last_observed for r in items)
        if since and last_seen < since:
            continue
        feed.append({
            "ioc_hash": ioc_hash,
            "ioc_type": items[0].ioc_type,
            "company_count": len({r.node_id for r in items}),
            "sectors": sorted({r.sector for r in items}),
            "regions": sorted({r.region for r in items}),
            "phishing_type": Counter(r.phishing_type for r in items).most_common(1)[0][0],
            "mitre_technique": Counter(r.mitre_technique for r in items).most_common(1)[0][0],
            "first_seen": min(r.first_observed for r in items),
            "last_seen": last_seen,
        })
    return sorted(feed, key=lambda item: item["last_seen"], reverse=True)


class DailyLimitExceeded(Exception):
    pass


def store_indicators(db: Session, node: Node, indicators) -> int:
    """Guarda el lote completo o nada, respetando el límite diario del nodo."""
    today = date.today()
    counter = db.get(DailyCount, {"node_id": node.id, "day": today})
    used = counter.count if counter else 0
    if used + len(indicators) > settings.daily_limit:
        raise DailyLimitExceeded()
    if counter is None:
        counter = DailyCount(node_id=node.id, day=today, count=0)
        db.add(counter)
    counter.count = used + len(indicators)

    existing = {r.ioc_hash: r for r in db.scalars(
        select(Report).where(Report.node_id == node.id,
                             Report.ioc_hash.in_([i.ioc_hash for i in indicators])))}
    for item in indicators:
        report = existing.get(item.ioc_hash)
        if report is None:
            report = Report(node_id=node.id, ioc_hash=item.ioc_hash, ioc_type=item.ioc_type,
                            phishing_type=item.phishing_type, mitre_technique=item.mitre_technique,
                            severity=item.severity, sector=item.sector, region=item.region,
                            first_observed=item.observed_on, last_observed=item.observed_on)
            db.add(report)
            existing[item.ioc_hash] = report
        else:
            report.last_observed = max(report.last_observed, item.observed_on)
            report.first_observed = min(report.first_observed, item.observed_on)
    db.commit()
    return len(indicators)


def operator_metrics(db: Session) -> dict:
    nodes = list(db.scalars(select(Node)))
    reports = _recent_reports(db)
    return {
        "nodes": dict(Counter(n.status for n in nodes)),
        "reports": len(reports),
        "indicators": len({r.ioc_hash for r in reports}),
        "visible_indicators": len(build_feed(db)),
    }
