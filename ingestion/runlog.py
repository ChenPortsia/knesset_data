"""Run logs: one log file per run, and run/table records in the `ops` schema of the raw database."""

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

LOG_DIR = Path("logs/ingestion")

DDL = """
CREATE SCHEMA IF NOT EXISTS ops;
CREATE TABLE IF NOT EXISTS ops.ingestion_runs (
    run_id VARCHAR PRIMARY KEY,
    mode VARCHAR,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    status VARCHAR,          -- ok | warn | failed
    tables_ok INTEGER,
    tables_warn INTEGER,
    tables_failed INTEGER,
    log_file VARCHAR
);
CREATE TABLE IF NOT EXISTS ops.ingestion_tables (
    run_id VARCHAR,
    table_name VARCHAR,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    status VARCHAR,          -- ok | warn | failed
    load_id VARCHAR,         -- dlt load id, matches _dlt_load_id in bronze
    rows_extracted BIGINT,   -- rows fetched from the API this run
    api_rows BIGINT,         -- rows the API has in scope
    bronze_rows BIGINT,      -- current rows in bronze
    deleted_rows BIGINT,     -- rows in bronze but no longer in the API (weekly check)
    max_updated_at TIMESTAMPTZ,
    warnings VARCHAR,
    error VARCHAR,
    PRIMARY KEY (run_id, table_name)
);
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE TABLE IF NOT EXISTS bronze.deleted_ids (
    table_name VARCHAR,      -- bronze table name, e.g. kns_bill
    id BIGINT,
    detected_at TIMESTAMPTZ,
    run_id VARCHAR
);
"""


def now() -> datetime:
    return datetime.now(UTC)


def new_run_id() -> str:
    return now().strftime("%Y%m%dT%H%M%SZ")


def setup_logging(run_id: str) -> Path:
    """Log to the console and to logs/ingestion/<run_id>.log."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"{run_id}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(log_file, encoding="utf-8")],
        force=True,
    )
    return log_file


def init(db: str) -> None:
    with duckdb.connect(db) as con:
        con.execute(DDL)


def insert(db: str, table: str, record: dict[str, Any]) -> None:
    """Insert or replace one record in an ops table."""
    columns = ", ".join(record)
    marks = ", ".join("?" for _ in record)
    with duckdb.connect(db) as con:
        con.execute(
            f"INSERT OR REPLACE INTO ops.{table} ({columns}) VALUES ({marks})",
            list(record.values()),
        )
