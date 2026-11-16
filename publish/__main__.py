"""Publish the agent's database: a copy of gold, context and rag, stamped with a data version.

    python -m publish        (make publish, after make dbt and make context)

The agent opens data/published/knesset.duckdb read-only. It holds the gold tables, the
context, and the protocol chunks with their vectors and keyword index (rag), when built.
Silver and bronze are not in it, so no query can reach them. `main.build_info` says which build an answer came from.
"""

import sys
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from context.search import build_keyword_index

ROOT = Path(__file__).resolve().parents[1]
WAREHOUSE = ROOT / "data" / "warehouse" / "warehouse.duckdb"
PUBLISHED = ROOT / "data" / "published" / "knesset.duckdb"
SCHEMAS = ("gold", "context", "rag")  # rag: the protocol chunks and their vectors, if built


def publish(warehouse: Path = WAREHOUSE, published: Path = PUBLISHED) -> str:
    """Write the published file and return its data version."""
    published.parent.mkdir(parents=True, exist_ok=True)
    new = published.with_suffix(".new")  # built aside, then swapped in, so readers never see half
    new.unlink(missing_ok=True)
    version = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with duckdb.connect(str(new)) as con:
        con.execute(f"ATTACH '{warehouse}' AS warehouse (READ_ONLY)")
        tables = con.execute(
            """
            SELECT table_schema, table_name FROM information_schema.tables
            WHERE table_catalog = 'warehouse' AND table_schema IN ? AND table_type = 'BASE TABLE'
            ORDER BY ALL
            """,
            [SCHEMAS],
        ).fetchall()
        for schema in SCHEMAS:
            con.execute(f"CREATE SCHEMA {schema}")
        for schema, table in tables:
            con.execute(
                f"CREATE TABLE {schema}.{table} AS SELECT * FROM warehouse.{schema}.{table}"
            )
        build_keyword_index(con)
        if ("rag", "chunks") in tables:
            build_keyword_index(con, "rag.chunks", "chunk_id", "chunk_text")
        con.execute(
            """
            CREATE TABLE build_info AS
            SELECT
                ? AS data_version,
                (SELECT MAX(vote_date) FROM gold.fct_plenum_vote) AS newest_vote_date,
                (SELECT MAX(session_date) FROM gold.fct_committee_session) AS newest_session_date,
                (SELECT built_at FROM context.build) AS context_built_at
            """,
            [version],
        )
        con.execute("DETACH warehouse")
    new.replace(published)
    print(f"published {len(tables)} tables to {published}, version {version}")
    return version


if __name__ == "__main__":
    publish()
    sys.exit(0)
