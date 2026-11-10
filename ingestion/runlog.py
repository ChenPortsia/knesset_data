"""Run logs: one log file per run, and run/table records in the `ops` schema of the raw database."""

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

LOG_DIR = Path("logs/ingestion")

DDL = """
create schema if not exists ops;
create table if not exists ops.ingestion_runs (
    run_id varchar primary key,
    mode varchar,
    started_at timestamptz,
    finished_at timestamptz,
    status varchar,          -- ok | warn | failed
    tables_ok integer,
    tables_warn integer,
    tables_failed integer,
    log_file varchar
);
create table if not exists ops.ingestion_tables (
    run_id varchar,
    table_name varchar,
    started_at timestamptz,
    finished_at timestamptz,
    status varchar,          -- ok | warn | failed
    load_id varchar,         -- dlt load id, matches _dlt_load_id in bronze
    rows_extracted bigint,   -- rows fetched from the API this run
    api_rows bigint,         -- rows the API has in scope
    bronze_rows bigint,      -- current rows in bronze
    deleted_rows bigint,     -- rows in bronze but no longer in the API (weekly check)
    max_updated_at timestamptz,
    warnings varchar,
    error varchar,
    primary key (run_id, table_name)
);
create schema if not exists bronze;
create table if not exists bronze.deleted_ids (
    table_name varchar,      -- bronze table name, e.g. kns_bill
    id bigint,
    detected_at timestamptz,
    run_id varchar
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
            f"insert or replace into ops.{table} ({columns}) values ({marks})",
            list(record.values()),
        )
