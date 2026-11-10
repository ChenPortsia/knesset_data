# knesset_data

Data platform for the Knesset agent: dlt ingests Knesset OData v4 and committee protocols into DuckDB, dbt models a star schema, and an NLP batch builds the search index.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the design and milestones, and [docs/questions.md](docs/questions.md) for what the warehouse must answer. The agent lives in [knesset-agent](https://github.com/ChenPortsia/knesset-agent).

## How the parts fit

```
Knesset OData API
      │  1. ingestion/       (dlt, Python)   make ingest / make sample
      ▼
bronze.*        raw tables, as the API returns them
      │  2. transformation/  (dbt, SQL)      make dbt
      ▼
silver.stg_*    staging: clean names, local times, decoded codes   ← done
silver.int_*    intermediate: joins and business logic             ← next
gold.dim_* / fct_*   marts: the star schema the agent queries
```

All layers live in one DuckDB file: `data/knesset.duckdb` (full load) or `data/knesset_sample.duckdb` (test load).

## Repo layout

```
ingestion/odata.py   # 1. Ingestion: OData API → bronze (dlt)
transformation/      # 2. Transformation: bronze → silver → gold (dbt project)
  models/staging/    #    one model per source table, 1:1, no joins
  models/intermediate/
  models/marts/
  seeds/             #    small CSVs: code labels (later: glossary, aliases)
  macros/            #    local_time(), code_label()
  tests/             #    custom SQL tests
nlp/                 # 3. NLP batch (milestone 4+)
notebooks/           # discovery and profiling of the source
docs/                # questions the warehouse must answer
tests/               # pytest unit tests for the Python code (no network)
data/                # DuckDB files and pipeline state, git-ignored
Makefile             # every command you need
```

## Quick start

```bash
uv sync                  # install dependencies
make sample              # test load: 200 rows per table (~30s)
make dbt TARGET=sample   # build and test the dbt models on the test load
make ingest              # full load (first run ~3h, then only changes)
make dbt                 # build and test on the full load
make docs TARGET=sample  # browse model and column docs
make test lint           # unit tests and lint
make clean               # delete all loaded data and pipeline state
```

Discovery notebook: `uv run --group notebook jupyter lab notebooks/01_odata_discovery.ipynb`.

## 1. Ingestion (`ingestion/odata.py`)

1. `TABLES` lists the 20 tables to load, each with an optional scope filter.
2. Scope: only the 20th Knesset onward (`FROM_KNESSET`, `FROM_DATE`), about 1.9M rows instead of 2.7M. Most of it is plenum vote results (1.35M rows).
3. Column types come from the API's `$metadata`, so every column exists even when it is empty in a load.
4. `fetch_pages` reads a table 100 rows at a time, ordered by `Id`, asking for `Id gt <last id>` each time (the API's `$skip` next links get slow on large tables).
5. Tables with `LastUpdatedDate` are incremental: dlt remembers the newest value, and the next run asks only for rows changed since then and merges them on `Id`. Tables without it are replaced.
6. dlt writes each table to `bronze.<table>` with snake_case names (`KNS_Person.LastUpdatedDate` → `bronze.kns_person.last_updated_date`) and records each load in `bronze._dlt_loads`. Pipeline state is kept in `data/.dlt`, so `make clean` resets everything.

## 2. Transformation (`transformation/`)

**Staging** (`models/staging/odata/`, schema `silver`): one view per bronze table, named `stg_odata__<entity>`. Each one only:

- renames columns to clear English names (`id` → `bill_id`, `mk_id` → `person_id`, `last_updated_date` → `updated_at`)
- converts timestamps to Israel local time (`local_time()` macro), so a vote at 01:45 falls on the right day
- adds English labels for codes from the `code_labels` seed (`code_label()` macro): vote result, bill origin, gender

Every model and column has an English | Hebrew description in `_odata__models.yml`. Each model's primary key is tested `unique` and `not_null`, and decoded codes are tested so a new code without a label fails the build.

Staging keeps all rows. Scoping link tables (bill initiators, session items) to the 20th Knesset happens in the intermediate layer, by joining to their parents.
