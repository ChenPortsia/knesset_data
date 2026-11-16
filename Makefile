# Two separate processes that share only the bronze tables:
#   1. ingestion       API -> data/raw/raw.duckdb (bronze, ops)
#   2. transformation  data/raw/raw.duckdb (read-only) -> data/warehouse/warehouse.duckdb (silver, gold)
# Run them directly (make ingest, make dbt) or as Docker services with HTTP APIs (make up).
#   3. context         context/*.yml + dbt docs -> data/warehouse/warehouse.duckdb (context schema)
TARGET ?= dev

.PHONY: up down sample ingest ingest-weekly protocols odata-survey peek-documents chunks embed embed-benchmark dbt answers metric publish ui context context-check context-approve context-schemas staging-models docs test lint clean

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

protocols:  ## Load committee protocols not loaded yet, e.g. make protocols ARGS='--committee "ועדת הכספים" --year 2024'
	uv run python -m ingestion.protocols $(ARGS)

odata-survey:  ## Profile the API tables we don't load into docs/odata_survey.md (loads nothing)
	uv run python -m ingestion.survey

peek-documents:  ## Look inside the newest committee and plenum protocol documents -> docs/document_peek.md
	uv run python -m ingestion.peek

dbt:  ## Transformation: build and test all models (TARGET=sample to use the test load)
	mkdir -p data/warehouse
	cd transformation && uv run dbt build --profiles-dir . --target $(TARGET)

chunks:  ## Cut the committee turns into chunks: gold.fct_turn -> rag.chunks (after make dbt)
	uv run python -m nlp chunk

embed:  ## Embed the chunks that have no vector yet (MODEL=potion, e5-large or e5-large-torch)
	uv run python -m nlp embed $(if $(MODEL),--model $(MODEL))

embed-benchmark:  ## Time every embedding model on 200 chunks (ARGS="--models e5-large-torch --sample 100" for one row)
	uv run python -m nlp benchmark $(ARGS)

metric:  ## Compute a MetricFlow metric, e.g. make metric M=bill_pass_rate BY=bill__knesset_num,bill__origin
	cd transformation && DBT_PROFILES_DIR=. uv run mf query --metrics $(M) $(if $(BY),--group-by $(BY))

context-check:  ## Check the context files: format, unique ids, references to gold (no data needed)
	cd transformation && uv run dbt parse --profiles-dir . --target $(TARGET) --quiet
	uv run python -m context check

context:  ## Check the context against the data, load and index it in the warehouse (after make dbt)
	cd transformation && uv run dbt compile --profiles-dir . --target $(TARGET) --quiet
	uv run python -m context build

publish:  ## Copy gold and context into the agent's database, data/published/knesset.duckdb (after make context)
	uv run python -m publish

ui:  ## Browse and query the databases in the browser (read-only; close it before make ingest / make dbt)
	uv run python scripts/ui.py

context-approve:  ## Store verified queries' current results as expected, e.g. make context-approve ID=vq.fastest_laws
	cd transformation && uv run dbt compile --profiles-dir . --target $(TARGET) --quiet
	uv run python -m context approve $(ID)

context-schemas:  ## Rewrite context/schemas/ after changing context/items.py
	uv run python -m context schemas

answers:  ## Answer the milestone 1 questions from gold (TARGET=sample for the test load)
	uv run python transformation/scripts/run_analyses.py --target $(TARGET)

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
