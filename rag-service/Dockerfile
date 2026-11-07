FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

COPY rag-service/pyproject.toml rag-service/uv.lock ./
COPY rag-service/src ./src
COPY config /config

RUN uv sync --frozen --no-dev --extra indexer

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libreoffice-writer \
        fonts-dejavu-core \
        fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/app/.venv/bin:$PATH"

CMD ["python", "-m", "rag_service"]
