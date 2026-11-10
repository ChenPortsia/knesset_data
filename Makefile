DB ?= data/knesset.duckdb
export KNESSET_DB := $(abspath $(DB))

.PHONY: all ingest dbt test lint

all: ingest dbt

ingest:  ## Load OData tables into bronze (pass TABLES="KNS_Person ..." for a subset)
	uv run python -m pipelines.odata $(TABLES)

dbt:
	cd dbt && uv run dbt build --profiles-dir .

test:
	uv run pytest -q

lint:
	uv run ruff check .
	uv run ruff format --check .
