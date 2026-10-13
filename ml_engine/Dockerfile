FROM python:3.11-slim
LABEL project="Sentryx" service="ml_engine"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt \
    && python -m nltk.downloader stopwords punkt
COPY . .
RUN useradd --no-create-home --shell /bin/false mluser \
    && chown -R mluser:mluser /app
USER mluser
EXPOSE 8001
