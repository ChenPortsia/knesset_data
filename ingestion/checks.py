"""Checks after each table load. They only warn: the data is already safely in bronze.

Blocking checks run earlier, while loading: `check_page` (Ids present and in order)
and dlt's schema contract (a changed column type fails the load).
"""

from datetime import datetime

import duckdb

from ingestion.odata import fetch_table

MIN_USUAL_ROWS = 100  # a table that usually changes this much per run should not return 0


def current_rows_sql(table: str, scd2: bool) -> str:
    return f"from bronze.{table}" + (" where _dlt_valid_to is null" if scd2 else "")


def bronze_stats(
    con: duckdb.DuckDBPyConnection, table: str, scd2: bool
) -> tuple[int, datetime | None]:
    """Current rows in bronze and the newest LastUpdatedDate (freshness)."""
    has_date = con.execute(
        "select count(*) from duckdb_columns() where schema_name = 'bronze' "
        "and table_name = ? and column_name = 'last_updated_date'",
        [table],
    ).fetchone()[0]
    newest = "max(last_updated_date)" if has_date else "null"
    return con.execute(f"select count(*), {newest} {current_rows_sql(table, scd2)}").fetchone()


def reconcile(api_rows: int, bronze_rows: int) -> str | None:
    """Bronze should hold exactly the rows the API has in scope."""
    if api_rows == bronze_rows:
        return None
    return f"bronze has {bronze_rows} rows, API has {api_rows} ({bronze_rows - api_rows:+})"


def volume(rows: int, usual_rows: float | None) -> str | None:
    """A table that usually changes should not suddenly return nothing."""
    if rows == 0 and usual_rows is not None and usual_rows >= MIN_USUAL_ROWS:
        return f"0 rows fetched, usually {usual_rows:.0f}"
    return None


def usual_rows(con: duckdb.DuckDBPyConnection, table: str) -> float | None:
    """Average rows fetched in the last 7 successful runs, skipping the first (full) load."""
    return con.execute(
        """
        select avg(rows_extracted) from (
            select t.rows_extracted, t.started_at
            from ops.ingestion_tables t join ops.ingestion_runs r using (run_id)
            where t.table_name = ? and t.status != 'failed' and r.mode != 'sample'
            qualify row_number() over (order by t.started_at) > 1
            order by t.started_at desc
            limit 7
        )
        """,
        [table],
    ).fetchone()[0]


def find_deleted(
    con: duckdb.DuckDBPyConnection, name: str, table: str, where: str | None, scd2: bool
) -> set[int]:
    """Ids still current in bronze but no longer in the API. Fetches only Ids."""
    api_ids = {row["Id"] for page in fetch_table(name, where, select="Id") for row in page}
    bronze_ids = {
        r[0] for r in con.execute(f"select id {current_rows_sql(table, scd2)}").fetchall()
    }
    return bronze_ids - api_ids
