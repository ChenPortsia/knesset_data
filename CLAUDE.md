# Knesset Agent

Personal project: a data platform (`knesset-data`) and a LangGraph multi-agent system (`knesset-agent`) over Knesset OData and committee protocols. The full design is in `ARCHITECTURE.md` — read it before starting any task.

## How to work here

- Keep code simple, short and clean. Prefer small, typed functions over frameworks and abstractions.
- Build one milestone at a time (see "Milestones" in `ARCHITECTURE.md`). Don't start the next one until the current one meets its "Done when".
- Current milestone: **2 — Context layer v1** (glossary, aliases, rules, verified queries and metrics in `knesset_data/context/`; `get_context`). Milestone 1 is done.

## Stack

Python, dlt, DuckDB, dbt-duckdb, LangGraph, Chainlit, Postgres (ops + context), Airflow, Langfuse.

## Conventions

- Knesset OData v4 base URL: `https://knesset.gov.il/OdataV4/ParliamentInfo/`. Page by key (`$filter=Id gt <last>` + `$orderby=Id`), not `@odata.nextLink`: its `$skip` links get slow on large tables.
- dbt layers: `staging` → `intermediate` → `marts`. Every model and column gets a Hebrew + English description.
- Agents never write to the warehouse; only the context layer, through one service function.
- Log runs and steps to the `ops` schema with shared IDs (`run_id`, `trace_id`, `session_id`, `user_id`, `data_version`).
