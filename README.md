# knesset_data

Data platform for the Knesset agent: dlt ingests Knesset OData v4 and committee protocols into DuckDB, dbt models a star schema, and an NLP batch builds the search index.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the design and milestones. The agent lives in [knesset-agent](https://github.com/ChenPortsia/knesset-agent).

## Repo layout

```
pipelines/odata.py   # dlt: Knesset OData → DuckDB schema `bronze`
dbt/                 # dbt: bronze → silver (staging, intermediate) → gold (marts)
nlp/                 # chunking, embeddings, topics (milestone 4+)
tests/               # pytest unit tests (no network)
data/                # the DuckDB file, git-ignored
Makefile             # every command you need
```

## Quick start

```bash
uv sync          # install dependencies
make sample      # test load: 200 rows per table into data/knesset_sample.duckdb (~30s)
make ingest      # full load into data/knesset.duckdb (first run ~3h, then only changes)
make test lint   # unit tests and lint
make clean       # delete all loaded data and pipeline state
```

## How the OData pipeline works

1. `TABLES` in `pipelines/odata.py` lists the tables to load, each with an optional scope filter.
2. Scope: only the 20th Knesset onward (`FROM_KNESSET`, `FROM_DATE`), about 1.6M rows instead of 2.8M. Most of it is plenum vote results (1.35M rows).
3. `fetch_pages` reads a table 100 rows at a time, ordered by `Id`, asking for `Id gt <last id>` each time.
4. Tables with `LastUpdatedDate` are incremental: dlt remembers the newest value, and the next run asks only for rows changed since then and merges them on `Id`. Tables without it are replaced.
5. dlt writes each table to `bronze.<table>` with snake_case names (`KNS_Person.LastUpdatedDate` → `bronze.kns_person.last_updated_date`) and records each load in `bronze._dlt_loads`. Pipeline state is kept in `data/.dlt`, so `make clean` resets everything.

Look at the data:

```bash
uv run python -c "import duckdb; print(duckdb.sql(\"from 'data/knesset_sample.duckdb'.bronze.kns_person limit 5\"))"
```
