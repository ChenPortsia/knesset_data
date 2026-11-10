# knesset_data

Data platform for the Knesset agent: dlt ingests Knesset OData v4 and committee protocols into DuckDB, dbt models a star schema, and an NLP batch builds the search index.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the design and milestones, and [docs/questions.md](docs/questions.md) for what the warehouse must answer. The agent lives in [knesset-agent](https://github.com/ChenPortsia/knesset-agent).

## How the parts fit

Two separate processes. They share only the bronze tables, each has its own dependencies and its own database file, and either can run, fail or be rebuilt without the other.

```
Knesset OData API
      │  1. ingestion/       (dlt, Python)   make ingest
      ▼
data/raw.duckdb          written only by ingestion
  bronze.*               every version of every row, as the API returns it
  ops.ingestion_*        one record per run and per table: status, counts, warnings
      │  2. transformation/  (dbt, SQL)      make dbt    (reads raw.duckdb read-only)
      ▼
data/warehouse.duckdb    written only by dbt
  silver.stg_*           staging: current rows, clean names, local times, decoded codes   ← done
  silver.int_*           intermediate: joins and business logic                          ← next
  gold.dim_* / fct_*     marts: the star schema the agent queries
```

Test loads use `data/raw_sample.duckdb` and `data/warehouse_sample.duckdb`.
DuckDB allows one writer per file, so run dbt after ingestion finishes, not during it.

## Repo layout

```
ingestion/           # 1. Ingestion: OData API → raw.duckdb (dlt)
  __main__.py        #    command line: one load per table, modes, run summary, exit code
  odata.py           #    API client, scope, paging, the dlt resource per table
  checks.py          #    checks after each load: reconciliation, volume, freshness, deletes
  runlog.py          #    log file per run and ops tables
transformation/      # 2. Transformation: raw.duckdb → warehouse.duckdb (dbt project)
  models/staging/    #    one model per source table, 1:1, no joins
  models/intermediate/
  models/marts/
  seeds/             #    small CSVs: code labels (later: glossary, aliases)
  macros/            #    current_rows(), local_time(), code_label()
  tests/             #    custom SQL tests
nlp/                 # 3. NLP batch (milestone 4+)
notebooks/           # discovery and profiling of the source
docs/                # questions the warehouse must answer
tests/               # pytest unit tests for the Python code (no network)
data/                # DuckDB files and pipeline state, git-ignored
logs/ingestion/      # one log file per ingestion run, git-ignored
Makefile             # every command you need
```

## Quick start

```bash
uv sync                  # install dependencies
make sample              # ingestion test load: 200 rows per table (~1 min)
make dbt TARGET=sample   # build and test the dbt models on the test load
make ingest              # ingestion: first run loads everything (~40 min), later runs only changes
make dbt                 # build and test on the full load
make ingest-weekly       # ingestion + check for rows deleted in the API (run weekly)
make docs TARGET=sample  # browse model and column docs
make test lint           # unit tests and lint
make clean               # delete all loaded data, pipeline state and logs
```

Discovery notebook: `uv run jupyter lab notebooks/01_odata_discovery.ipynb`.

## 1. Ingestion (`ingestion/`)

**What it loads.** `TABLES` in `odata.py` lists 20 tables, each with an optional scope filter: only the 20th Knesset onward (`FROM_KNESSET`, `FROM_DATE`), about 1.9M rows instead of 2.7M. Most of it is plenum vote results (1.35M rows).

**How it loads.**
- One dlt load per table, so a failing table never loses the others. The run continues, records the failure and exits with code 1.
- Paging by `Id` (`Id gt <last id>`), because the API's `$skip` next links get slow on large tables. Large tables are split into up to 8 `Id` ranges fetched in parallel.
- Column types come from the API's `$metadata`, so every column exists even when it is empty.
- Incremental on `LastUpdatedDate`: each run asks only for rows changed since the last run, minus a 1-hour overlap for rows committed late.
- Bronze keeps **every version of every row** (dlt SCD2): `_dlt_valid_from` / `_dlt_valid_to`, and the current version has `_dlt_valid_to` null. This is how we get history the API doesn't keep, such as a bill's status over time. A row that didn't change produces the same row hash, so reruns and the overlap add nothing.
- Only technical changes: dlt's snake_case names (`KNS_Person.LastUpdatedDate` → `bronze.kns_person.last_updated_date`) and parsing `LastUpdatedDate` for the cursor. Everything else happens in dbt.

**Checks.**

| Check | When | On failure |
| --- | --- | --- |
| Every row has an `Id`, in increasing order | each page | table fails, nothing saved |
| Column types unchanged (dlt schema contract) | each load | table fails, nothing saved |
| New columns in the API | each load | added and logged |
| Bronze rows = API `$count` in scope (reconciliation) | after each load | warning |
| 0 rows fetched for a table that usually changes (volume) | after each load | warning |
| Newest `LastUpdatedDate` (freshness) | after each load | recorded |
| Rows deleted in the API (Id-only comparison) | weekly | recorded in `bronze.deleted_ids`, dbt leaves them out |

**Errors.** Each request is retried up to 5 times with backoff on HTTP 429, 5xx and lost connections (dlt defaults), with a 120-second timeout. A load is all-or-nothing, and incremental state is saved only when it succeeds, so a rerun picks up exactly where it should.

**Logs.** Each run writes `logs/ingestion/<run_id>.log` and records in `data/raw.duckdb`:

```sql
select * from ops.ingestion_runs order by started_at desc;    -- one row per run
select * from ops.ingestion_tables where status != 'ok';      -- per table: counts, warnings, errors
```

`ops.ingestion_tables.load_id` matches `_dlt_load_id` on the bronze rows that load wrote.

## 2. Transformation (`transformation/`)

dbt opens `raw.duckdb` read-only as the `raw` database and writes to `warehouse.duckdb`, so it can never change bronze.

**Staging** (`models/staging/odata/`, schema `silver`): one view per bronze table, named `stg_odata__<entity>`. Each one only:

- reads the current version of each row and leaves out rows deleted in the API (`current_rows()` macro)
- renames columns to clear English names (`id` → `bill_id`, `mk_id` → `person_id`, `last_updated_date` → `updated_at`)
- converts timestamps to Israel local time (`local_time()` macro), so a vote at 01:45 falls on the right day
- adds English labels for codes from the `code_labels` seed (`code_label()` macro): vote result, bill origin, gender

Every model and column has an English | Hebrew description in `_odata__models.yml`. Each model's primary key is tested `unique` and `not_null`, and decoded codes are tested so a new code without a label fails the build.

Staging keeps all rows. Scoping link tables (bill initiators, session items) to the 20th Knesset happens in the intermediate layer, by joining to their parents.
