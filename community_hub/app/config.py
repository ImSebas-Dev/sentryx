"""Configuración del hub. Todo sale de variables de entorno (ver docker-compose.yml)."""
import os


class Settings:
    database_url = os.environ.get("COMMUNITY_HUB_DATABASE_URL", "sqlite:///./community_hub.db")
    # Sin clave de operador el panel y la aprobación de nodos quedan cerrados
    operator_key = os.environ.get("COMMUNITY_HUB_OPERATOR_KEY", "")
    k_anonymity = int(os.environ.get("COMMUNITY_K_ANONYMITY", "2"))
    daily_limit = int(os.environ.get("COMMUNITY_DAILY_LIMIT", "1000"))
    max_pending_nodes = int(os.environ.get("COMMUNITY_MAX_PENDING_NODES", "100"))
    # Solo cuenta lo observado en esta ventana: una campaña vieja no es un aviso temprano
    retention_days = int(os.environ.get("COMMUNITY_RETENTION_DAYS", "90"))


settings = Settings()
