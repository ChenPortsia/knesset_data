DB ?= data/knesset.duckdb
export KNESSET_DB := $(abspath $(DB))

.PHONY: all ingest dbt

all: ingest dbt

ingest:
	uv run python -m pipelines.odata

dbt:
	cd dbt && uv run dbt build --profiles-dir .
