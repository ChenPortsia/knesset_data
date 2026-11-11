# Two separate processes that share only the bronze tables:
#   1. ingestion       API -> data/raw/raw.duckdb (bronze, ops)
#   2. transformation  data/raw/raw.duckdb (read-only) -> data/warehouse/warehouse.duckdb (silver, gold)
# Run them directly (make ingest, make dbt) or as Docker services with HTTP APIs (make up).
TARGET ?= dev

.PHONY: up down sample ingest ingest-weekly dbt staging-models docs test lint clean

up:  ## Start both services in Docker: ingestion on :8001, transformation on :8002
	mkdir -p data/raw data/warehouse logs
	docker compose up -d --build

down:  ## Stop the Docker services
	docker compose down

sample:  ## Ingestion test load: 200 rows per table into data/raw/raw_sample.duckdb (~1 min)
	uv run python -m ingestion --mode sample $(TABLES)

ingest:  ## Ingestion daily run: changed rows only (first run loads everything, ~40 min)
	uv run python -m ingestion --mode daily $(TABLES)

ingest-weekly:  ## Ingestion weekly run: daily + check for rows deleted in the API
	uv run python -m ingestion --mode weekly $(TABLES)

dbt:  ## Transformation: build and test all models (TARGET=sample to use the test load)
	mkdir -p data/warehouse
	cd transformation && uv run dbt build --profiles-dir . --target $(TARGET)

staging-models:  ## Regenerate the dbt staging models (SQL + YAML) from the spec and the API's $metadata
	uv run python transformation/scripts/generate_staging.py

docs:  ## Browse model and column docs at http://localhost:8080
	cd transformation && uv run dbt docs generate --profiles-dir . --target $(TARGET) && uv run dbt docs serve --profiles-dir . --port 8080

test:
	uv run pytest -q

lint:
	uv run ruff check .
	uv run ruff format --check .

clean:  ## Delete all loaded data, pipeline state and logs
	rm -rf data/ logs/
