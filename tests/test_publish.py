"""The published database holds gold and context only, with a data version."""

from datetime import date

import duckdb

from context.search import build_index
from publish.__main__ import publish


def test_publish_copies_gold_and_context_only(tmp_path):
    warehouse = tmp_path / "warehouse.duckdb"
    with duckdb.connect(str(warehouse)) as con:
        con.execute(
            """
            CREATE SCHEMA silver; CREATE SCHEMA gold; CREATE SCHEMA context;
            CREATE TABLE silver.stg_bill AS SELECT 1 AS bill_id;
            CREATE TABLE gold.fct_plenum_vote AS SELECT DATE '2026-07-01' AS vote_date;
            CREATE TABLE gold.fct_committee_session AS SELECT DATE '2026-07-02' AS session_date;
            CREATE TABLE context.items AS
            SELECT 'glossary.law' AS id, 'law' AS title, 'A passed bill' AS text, 'חוק' AS text_he;
            """
        )
        build_index(con, embed=lambda texts: [[1.0, 0.0] for _ in texts], model="fake")

    version = publish(warehouse, tmp_path / "published" / "knesset.duckdb")

    with duckdb.connect(str(tmp_path / "published" / "knesset.duckdb"), read_only=True) as con:
        schemas = {r[0] for r in con.execute("SELECT schema_name FROM duckdb_tables()").fetchall()}
        assert "silver" not in schemas and {"gold", "context"} <= schemas
        assert con.execute("SELECT data_version, newest_vote_date FROM build_info").fetchall() == [
            (version, date(2026, 7, 1))
        ]
        con.execute("LOAD fts")
        found = con.execute(
            """
            SELECT id FROM context.search
            WHERE fts_context_search.match_bm25(id, 'חוק') IS NOT NULL
            """
        ).fetchall()
        assert found == [("glossary.law",)]
