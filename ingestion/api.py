"""HTTP API to trigger and watch ingestion runs. Run: uvicorn ingestion.api:app

Each run is `python -m ingestion` in a background process, one at a time.
Interactive docs at /docs.
"""

import sys
from pathlib import Path
from typing import Any, Literal

import duckdb
from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from common.jobs import Job, Runner, tail
from ingestion.odata import TABLES, load_settings, scope
from ingestion.runlog import LOG_DIR, new_run_id

DBS = {
    "daily": "data/raw/raw.duckdb",
    "weekly": "data/raw/raw.duckdb",
    "sample": "data/raw/raw_sample.duckdb",
}

app = FastAPI(
    title="Knesset ingestion", description="Load Knesset OData tables into data/raw/raw.duckdb"
)
runner = Runner(LOG_DIR)


class RunRequest(BaseModel):
    mode: Literal["daily", "weekly", "sample"] = "daily"
    tables: list[str] = []  # default: all tables


def query_ops(db: str, sql: str, params: list[Any]) -> list[dict[str, Any]]:
    """Rows from the ops tables, read-only. Fails while a run holds the database."""
    if not Path(db).exists():
        return []
    with duckdb.connect(db, read_only=True) as con:
        cursor = con.execute(sql, params)
        columns = [c[0] for c in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def ops_or_busy(db: str, sql: str, params: list[Any]) -> list[dict[str, Any]]:
    if runner.current:
        raise HTTPException(409, "a run is in progress; its history is readable when it ends")
    return query_ops(db, sql, params)


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "running": runner.current.job_id if runner.current else None}


@app.get("/tables")
def tables() -> dict[str, dict[str, Any]]:
    """The tables ingestion loads, with their scope filter (from ingestion/.dlt/config.toml)."""
    settings = load_settings()
    return {
        name: {"scope": scope(name, settings), "incremental": t.incremental}
        for name, t in TABLES.items()
    }


@app.post("/runs", status_code=202)
def start_run(request: RunRequest) -> Job:
    """Start a run. 409 if one is already running."""
    if unknown := set(request.tables) - set(TABLES):
        raise HTTPException(422, f"unknown tables: {sorted(unknown)}")
    run_id = new_run_id()
    command = [sys.executable, "-m", "ingestion", "--mode", request.mode, "--run-id", run_id]
    job = runner.start(run_id, command + request.tables)
    if job is None:
        raise HTTPException(409, f"run {runner.current.job_id} is still running")
    return job


@app.get("/runs")
def list_runs(mode: Literal["daily", "sample"] = "daily", limit: int = 20) -> dict[str, Any]:
    """The run in progress, if any, and recent finished runs from ops.ingestion_runs."""
    recent = None if runner.current else query_ops(
        DBS[mode], "SELECT * FROM ops.ingestion_runs ORDER BY started_at DESC LIMIT ?", [limit]
    )  # fmt: skip
    return {"running": runner.current, "recent": recent}


@app.get("/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    """A run's status; when finished, its per-table results from ops.ingestion_tables."""
    job = runner.jobs.get(run_id)
    if job and job.status == "running":
        return {"run": job, "log_tail": tail(LOG_DIR / f"{run_id}.log", 30)}
    for db in sorted(set(DBS.values())):
        runs = ops_or_busy(db, "SELECT * FROM ops.ingestion_runs WHERE run_id = ?", [run_id])
        if runs:
            sql = "SELECT * FROM ops.ingestion_tables WHERE run_id = ? ORDER BY started_at"
            return {"run": runs[0], "tables": ops_or_busy(db, sql, [run_id]), "job": job}
    if job:  # finished but recorded nothing: it crashed before the end, see its log
        return {"run": job, "log_tail": tail(job.log_file, 50)}
    raise HTTPException(404, f"no run {run_id}")


@app.get("/runs/{run_id}/log", response_class=PlainTextResponse)
def get_log(run_id: str, lines: int = 500) -> str:
    """The run's log file (falls back to raw console output if the run crashed early)."""
    for name in (f"{run_id}.log", f"{run_id}.out"):
        if text := tail(LOG_DIR / name, lines):
            return text
    raise HTTPException(404, f"no log for run {run_id}")
