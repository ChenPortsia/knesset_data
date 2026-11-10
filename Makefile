.PHONY: all sample ingest dbt test lint clean

all: ingest dbt

sample:  ## Test load: 200 rows per table into data/knesset_sample.duckdb (~1 min)
	uv run python -m pipelines.odata --sample $(TABLES)

ingest:  ## Full load into data/knesset.duckdb (pass TABLES="KNS_Person ..." for a subset)
	uv run python -m pipelines.odata $(TABLES)

dbt:
	cd dbt && uv run dbt build --profiles-dir .

test:
	uv run pytest -q

lint:
	uv run ruff check .
	uv run ruff format --check .

clean:  ## Delete all loaded data and pipeline state
	rm -rf data/
