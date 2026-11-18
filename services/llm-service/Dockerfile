# AEIP intelligence API (Python). Build from services/llm-service:
#   docker build -t aeip-intelligence services/llm-service
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    AEIP_HOST=0.0.0.0 PORT=8001 HF_HOME=/app/models
WORKDIR /app

RUN useradd --create-home --uid 10001 aeip
COPY requirements.txt .
RUN pip install -r requirements.txt

# Bake the local embedding model into the image (no download at start-up). Skip with --build-arg PRELOAD_MODEL=0.
ARG PRELOAD_MODEL=1
RUN if [ "$PRELOAD_MODEL" = "1" ]; then python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')"; fi

COPY src ./src
COPY scripts ./scripts
COPY data/demo_repository.json data/demo_events.json ./data/
RUN mkdir -p data/cache && chown -R aeip:aeip /app
USER aeip

EXPOSE 8001
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8001\")}/health', timeout=4)"
CMD ["python", "scripts/serve.py"]
