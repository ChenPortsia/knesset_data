"""HTTP API to trigger and watch dbt builds. Run: uvicorn transformation.api:app

Each build is `dbt build` in a background process, one at a time. dbt reads
data/raw.duckdb read-only and writes data/warehouse.duckdb, so start a build after
an ingestion run has finished. Interactive docs at /docs.
"""

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from common.jobs import Job, Runner, now, tail

PROJECT_DIR = Path(__file__).parent
LOG_DIR = Path("logs/transformation")
DBT = str(Path(sys.executable).parent / "dbt")  # the dbt installed next to this Python


def summarize(job: Job) -> dict[str, Any] | None:
    """Counts by status and the failures, from dbt's target/run_results.json."""
    path = PROJECT_DIR / "target" / "run_results.json"
    if not path.exists() or path.stat().st_mtime < job.started_at.timestamp():
        return None  # dbt stopped before writing results; see the log
    results = json.loads(path.read_text())["results"]
    failures = [
        {"node": r["unique_id"], "status": r["status"], "message": r.get("message")}
        for r in results
        if r["status"] in ("error", "fail", "warn")
    ]
    return {"counts": dict(Counter(r["status"] for r in results)), "failures": failures}


app = FastAPI(
    title="Knesset transformation", description="Build the dbt models into data/warehouse.duckdb"
)
runner = Runner(LOG_DIR, cwd=PROJECT_DIR, on_finish=summarize)


class BuildRequest(BaseModel):
    target: Literal["dev", "sample"] = "dev"  # dev: full load, sample: test load
    select: str | None = None  # dbt node selection, e.g. "staging" or "stg_odata__bill+"


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "running": runner.current.job_id if runner.current else None}


@app.post("/builds", status_code=202)
def start_build(request: BuildRequest) -> Job:
    """Start `dbt build`. 409 if a build is already running."""
    build_id = now().strftime("%Y%m%dT%H%M%SZ")
    command = [DBT, "build", "--profiles-dir", ".", "--target", request.target]
    job = runner.start(build_id, command + (["--select", request.select] if request.select else []))
    if job is None:
        raise HTTPException(409, f"build {runner.current.job_id} is still running")
    return job


@app.get("/builds")
def list_builds() -> list[Job]:
    """Builds since the service started, newest first."""
    return sorted(runner.jobs.values(), key=lambda job: job.started_at, reverse=True)


@app.get("/builds/{build_id}")
def get_build(build_id: str) -> Job:
    """A build's status; when finished, its result counts and failures."""
    if job := runner.jobs.get(build_id):
        return job
    raise HTTPException(404, f"no build {build_id} since the service started")


@app.get("/builds/{build_id}/log", response_class=PlainTextResponse)
def get_log(build_id: str, lines: int = 500) -> str:
    if text := tail(LOG_DIR / f"{build_id}.out", lines):
        return text
    raise HTTPException(404, f"no log for build {build_id}")
