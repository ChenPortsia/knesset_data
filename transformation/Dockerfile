# Transformation service: dbt builds raw.duckdb (read-only) -> warehouse.duckdb, over HTTP.
# Build from the repo root: docker build -f transformation/Dockerfile .
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 DBT_SEND_ANONYMOUS_USAGE_STATS=false
WORKDIR /app

# Dependencies first, so code changes don't reinstall them. Only this service's groups.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-default-groups --group transformation --group api

COPY common/ common/
COPY transformation/ transformation/
RUN cd transformation && dbt parse --profiles-dir .  # fail the image build on a broken project

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn", "transformation.api:app", "--host", "0.0.0.0", "--port", "8000"]
