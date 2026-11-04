"""
Sentryx — Hub de la Red de alerta entre pymes.

Servicio opcional: se levanta solo con `docker compose --profile hub up`.
Recibe hashes de indicadores y publica únicamente los que reportaron al menos K
nodos, sin revelar nunca quién los reportó.
"""
import secrets
from contextlib import asynccontextmanager
from datetime import date

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app import logic
from app.config import settings
from app.db import Base, engine, get_db
from app.models import Node, Report
from app.operator_panel import PANEL_HTML
from app.schemas import (
    ClaimRequest, ClaimResponse, Feed, IndicatorBatch, RegisterRequest, RegisterResponse,
)


@asynccontextmanager
async def lifespan(_app):
    Base.metadata.create_all(engine)
    yield


# Deja cerrada la documentación automática: este servicio queda expuesto a internet
app = FastAPI(title="Sentryx Community Hub", version="1.0", lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)
basic_auth = HTTPBasic(auto_error=False)


@app.get("/health")
def health():
    return {"status": "ok", "service": "community_hub"}


# ── Autenticación de nodos ────────────────────────────────
def current_node(x_node_key: str = Header(default=""), db: Session = Depends(get_db)) -> Node:
    node = logic.find_node_by_key(db, x_node_key)
    if node is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Key de nodo inválida.")
    return node


def active_node(node: Node = Depends(current_node)) -> Node:
    if node.status != "active":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Este nodo está suspendido.")
    return node


# ── Registro ──────────────────────────────────────────────
@app.post("/nodes/register", response_model=RegisterResponse, status_code=201)
def register_node(body: RegisterRequest, db: Session = Depends(get_db)):
    # Este endpoint es público: limita los pendientes para que no llenen la base
    pending = db.scalar(select(func.count()).select_from(Node).where(Node.status == "pending"))
    if pending >= settings.max_pending_nodes:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Hay demasiados registros pendientes.")
    token = logic.new_secret()
    node = Node(name=body.name, sector=body.sector, region=body.region,
                registration_hash=logic.hash_secret(token))
    db.add(node)
    db.commit()
    return RegisterResponse(node_id=node.id, registration_token=token, status=node.status)


@app.post("/nodes/claim", response_model=ClaimResponse)
def claim_key(body: ClaimRequest, db: Session = Depends(get_db)):
    """
    Entrega la key una sola vez, cuando el operador ya aprobó el nodo. Se genera aquí
    y no al aprobar para que ni el operador llegue a verla.
    """
    node = db.get(Node, body.node_id)
    token_ok = (node is not None and node.registration_hash is not None and
                secrets.compare_digest(node.registration_hash,
                                       logic.hash_secret(body.registration_token)))
    if not token_ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Registro inválido o key ya entregada.")
    if node.status == "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, "El operador aún no aprueba este nodo.")
    if node.status != "active":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Este nodo está suspendido.")
    api_key = logic.new_secret()
    node.key_hash = logic.hash_secret(api_key)
    node.registration_hash = None
    db.commit()
    return ClaimResponse(node_api_key=api_key)


# ── Indicadores ───────────────────────────────────────────
@app.post("/indicators")
def post_indicators(body: IndicatorBatch, node: Node = Depends(active_node),
                    db: Session = Depends(get_db)):
    try:
        accepted = logic.store_indicators(db, node, body.indicators)
    except logic.DailyLimitExceeded:
        db.rollback()
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Se superó el límite diario del nodo.")
    return {"accepted": accepted}


@app.get("/feed", response_model=Feed)
def get_feed(since: date | None = Query(default=None), _node: Node = Depends(active_node),
             db: Session = Depends(get_db)):
    return Feed(indicators=logic.build_feed(db, since))


@app.delete("/nodes/me/indicators")
def delete_my_indicators(node: Node = Depends(current_node), db: Session = Depends(get_db)):
    # Permite borrar también a un nodo suspendido: retirar sus datos es su derecho
    result = db.execute(delete(Report).where(Report.node_id == node.id))
    db.commit()
    return {"deleted": result.rowcount}


# ── Panel del operador ────────────────────────────────────
def require_operator(credentials: HTTPBasicCredentials | None = Depends(basic_auth)):
    if not settings.operator_key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Configura COMMUNITY_HUB_OPERATOR_KEY para usar el panel.")
    valid = credentials is not None and secrets.compare_digest(
        credentials.password.encode(), settings.operator_key.encode())
    if not valid:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Credenciales inválidas.",
                            headers={"WWW-Authenticate": 'Basic realm="Sentryx Hub"'})


def require_operator_action(x_operator_action: str = Header(default=""),
                            _auth=Depends(require_operator)):
    # El navegador reenvía Basic Auth solo: exige este encabezado, que otro sitio no
    # puede agregar sin permiso CORS, para que un enlace ajeno no apruebe nodos (CSRF).
    if x_operator_action != "1":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Falta el encabezado X-Operator-Action.")


@app.get("/operator", response_class=HTMLResponse, dependencies=[Depends(require_operator)])
def operator_panel():
    return HTMLResponse(PANEL_HTML, headers={
        "Content-Security-Policy": "default-src 'self'; style-src 'unsafe-inline'; "
                                   "script-src 'unsafe-inline'; connect-src 'self'",
        "X-Frame-Options": "DENY",
    })


@app.get("/operator/nodes", dependencies=[Depends(require_operator)])
def operator_nodes(db: Session = Depends(get_db)):
    counts = dict(db.execute(select(Report.node_id, func.count()).group_by(Report.node_id)).all())
    reputations = logic.compute_reputations(list(db.scalars(select(Report))))
    return [{
        "id": node.id, "name": node.name, "sector": node.sector, "region": node.region,
        "status": node.status, "established": node.established,
        "created_at": node.created_at, "approved_at": node.approved_at,
        "reports": counts.get(node.id, 0),
        "reputation": round(reputations.get(node.id, 1.0), 2),
    } for node in db.scalars(select(Node).order_by(Node.created_at.desc()))]


@app.get("/operator/metrics", dependencies=[Depends(require_operator)])
def metrics(db: Session = Depends(get_db)):
    return logic.operator_metrics(db)


def _get_node(db: Session, node_id: str) -> Node:
    node = db.get(Node, node_id)
    if node is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El nodo no existe.")
    return node


@app.post("/operator/nodes/{node_id}/approve", dependencies=[Depends(require_operator_action)])
def approve_node(node_id: str, established: bool = False, db: Session = Depends(get_db)):
    """established=true omite el periodo de prueba de un nodo que el operador ya conoce."""
    node = _get_node(db, node_id)
    node.status = "active"
    node.established = established
    node.approved_at = node.approved_at or logic.utcnow()
    db.commit()
    return {"id": node.id, "status": node.status}


@app.post("/operator/nodes/{node_id}/suspend", dependencies=[Depends(require_operator_action)])
def suspend_node(node_id: str, db: Session = Depends(get_db)):
    node = _get_node(db, node_id)
    node.status = "suspended"
    db.commit()
    return {"id": node.id, "status": node.status}
