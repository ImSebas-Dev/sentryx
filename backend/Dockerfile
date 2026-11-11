FROM python:3.11-slim
LABEL project="Sentryx" service="backend"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
# Solo curl (healthcheck). Sin compiladores en la imagen: todas las
# dependencias se instalan desde wheels precompilados.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt
COPY . .
# staticfiles debe existir en la imagen con dueño appuser: Docker inicializa el
# volumen static_files con este directorio (si no, queda de root y collectstatic falla)
RUN mkdir -p /app/staticfiles \
    && useradd --no-create-home --shell /bin/false appuser \
    && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
