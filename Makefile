TARGET ?= dev

.PHONY: all sample ingest dbt docs test lint clean

all: ingest dbt

sample:  ## Test load: 200 rows per table into data/knesset_sample.duckdb (~1 min)
	uv run python -m ingestion.odata --sample $(TABLES)

ingest:  ## Full load into data/knesset.duckdb (pass TABLES="KNS_Person ..." for a subset)
	uv run python -m ingestion.odata $(TABLES)

dbt:  ## Build and test all dbt models (TARGET=sample to use the test load)
	cd transformation && uv run dbt build --profiles-dir . --target $(TARGET)

docs:  ## Browse model and column docs at http://localhost:8080
	cd transformation && uv run dbt docs generate --profiles-dir . --target $(TARGET) && uv run dbt docs serve --profiles-dir . --port 8080

test:
	uv run pytest -q

lint:
	uv run ruff check .
	uv run ruff format --check .

clean:  ## Delete all loaded data and pipeline state
	rm -rf data/
