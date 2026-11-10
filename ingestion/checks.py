"""Checks after each table load. They only warn: the data is already safely in bronze.

Blocking checks run earlier, while loading: `clean_page` (Ids present and in order)
and dlt's schema contract (a changed column type fails the load).
"""

from datetime import datetime

import duckdb

from ingestion.odata import GetJson, fetch_table

MIN_USUAL_ROWS = 100  # a table that usually changes this much per run should not return 0


def current_rows_sql(table: str, scd2: bool) -> str:
    return f"FROM bronze.{table}" + (" WHERE _dlt_valid_to IS NULL" if scd2 else "")


def bronze_stats(
    con: duckdb.DuckDBPyConnection, table: str, scd2: bool
) -> tuple[int, datetime | None]:
    """Current rows in bronze and the newest LastUpdatedDate (freshness)."""
    has_date = con.execute(
        """
        SELECT COUNT(*)
        FROM duckdb_columns()
        WHERE schema_name = 'bronze' AND table_name = ? AND column_name = 'last_updated_date'
        """,
        [table],
    ).fetchone()[0]
    newest = "MAX(last_updated_date)" if has_date else "NULL"
    return con.execute(f"SELECT COUNT(*), {newest} {current_rows_sql(table, scd2)}").fetchone()


def reconcile(api_rows: int, bronze_rows: int) -> str | None:
    """Bronze should hold the rows the API has in scope (fewer if the API repeats Ids)."""
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
        SELECT AVG(rows_extracted)
        FROM (
            SELECT t.rows_extracted, t.started_at
            FROM ops.ingestion_tables AS t
            JOIN ops.ingestion_runs AS r USING (run_id)
            WHERE t.table_name = ? AND t.status != 'failed' AND r.mode != 'sample'
            QUALIFY ROW_NUMBER() OVER (ORDER BY t.started_at) > 1
            ORDER BY t.started_at DESC
            LIMIT 7
        )
        """,
        [table],
    ).fetchone()[0]


def find_deleted(
    con: duckdb.DuckDBPyConnection,
    get: GetJson,
    name: str,
    table: str,
    where: str | None,
    scd2: bool,
    workers: int,
) -> set[int]:
    """Ids still current in bronze but no longer in the API. Fetches only Ids."""
    pages = fetch_table(get, name, where, select="Id", workers=workers)
    api_ids = {row["Id"] for page in pages for row in page}
    bronze_ids = {
        r[0] for r in con.execute(f"SELECT id {current_rows_sql(table, scd2)}").fetchall()
    }
    return bronze_ids - api_ids
