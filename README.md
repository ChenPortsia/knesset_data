# knesset-data

Data platform for the Knesset agent: dlt ingests Knesset OData v4 and committee protocols into DuckDB, dbt models a star schema, and an NLP batch builds the search index.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the design and milestones. The agent lives in [knesset-agent](https://github.com/ChenPortsia/knesset-agent).

## Quick start

```bash
uv sync
make all
```
