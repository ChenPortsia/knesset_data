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
uv sync                                   # install dependencies
make ingest TABLES="KNS_Person KNS_Faction"   # load a few tables (~30s)
make ingest                               # load all tables (first run takes hours, then only changes)
make test lint                            # unit tests and lint
```

## How the OData pipeline works

1. `TABLES` in `pipelines/odata.py` lists the tables to load.
2. `fetch_pages` reads a table 100 rows at a time, ordered by `Id`, asking for `Id gt <last id>` each time.
3. Tables with `LastUpdatedDate` are incremental: dlt remembers the newest value, and the next run asks only for rows changed since then and merges them on `Id`. Tables without it are replaced.
4. dlt writes each table to `bronze.<table>` in `data/knesset.duckdb`, with snake_case names (`KNS_Person.LastUpdatedDate` → `bronze.kns_person.last_updated_date`), and records each load in `bronze._dlt_loads`.

Look at the data:

```bash
uv run python -c "import duckdb; print(duckdb.sql(\"from 'data/knesset.duckdb'.bronze.kns_person limit 5\"))"
```
