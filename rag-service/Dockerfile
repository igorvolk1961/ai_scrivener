FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

COPY rag-service/pyproject.toml rag-service/uv.lock ./
COPY rag-service/src ./src
COPY config /app/config

RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

CMD ["python", "-m", "rag_service"]
