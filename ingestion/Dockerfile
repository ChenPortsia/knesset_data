# Ingestion service: OData API -> data/raw/raw.duckdb, triggered over HTTP (see ingestion/api.py).
# Build from the repo root: docker build -f ingestion/Dockerfile .
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1
WORKDIR /app

# Dependencies first, so code changes don't reinstall them. Only this service's groups.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-default-groups --group ingestion --group api

COPY common/ common/
COPY ingestion/ ingestion/

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn", "ingestion.api:app", "--host", "0.0.0.0", "--port", "8000"]
