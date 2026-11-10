import json
import os
import sys
import time

import pytest
from fastapi.testclient import TestClient

import ingestion.api
import transformation.api
from common.jobs import Job, Runner

SLEEP = [sys.executable, "-c", "import time; time.sleep(30)"]


def wait(job: Job, seconds: float = 10) -> Job:
    deadline = time.time() + seconds
    while job.status == "running" and time.time() < deadline:
        time.sleep(0.05)
    return job


def test_runner_records_success_failure_and_output(tmp_path):
    runner = Runner(tmp_path)
    ok = wait(runner.start("ok", [sys.executable, "-c", "print('hello')"]))
    assert (ok.status, ok.exit_code) == ("succeeded", 0)
    assert open(ok.log_file).read() == "hello\n"
    assert wait(runner.start("bad", [sys.executable, "-c", "raise SystemExit(3)"])).exit_code == 3
    assert wait(runner.start("missing", ["no-such-command"])).status == "failed"


def test_runner_runs_one_job_at_a_time(tmp_path):
    runner = Runner(tmp_path)
    first = runner.start("first", SLEEP)
    assert runner.start("second", SLEEP) is None
    assert runner.current is first


@pytest.fixture
def ingestion_client(tmp_path, monkeypatch):
    monkeypatch.setattr(ingestion.api, "runner", Runner(tmp_path))
    return TestClient(ingestion.api.app)


def test_ingestion_health_and_tables(ingestion_client):
    assert ingestion_client.get("/health").json() == {"status": "ok", "running": None}
    tables = ingestion_client.get("/tables").json()
    assert tables["KNS_Bill"] == {"scope": "KnessetNum ge 20", "incremental": True}


def test_ingestion_rejects_unknown_tables_and_a_second_run(ingestion_client):
    assert ingestion_client.post("/runs", json={"tables": ["KNS_Nope"]}).status_code == 422
    ingestion.api.runner.start("busy", SLEEP)
    response = ingestion_client.post("/runs", json={"mode": "sample"})
    assert response.status_code == 409
    assert ingestion_client.get("/health").json()["running"] == "busy"


def test_ingestion_unknown_run(ingestion_client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # no data/ here
    assert ingestion_client.get("/runs/nope").status_code == 404


def test_transformation_summarizes_dbt_results(tmp_path, monkeypatch):
    monkeypatch.setattr(transformation.api, "PROJECT_DIR", tmp_path)
    job = Job("b1", ["dbt"], "log", started_at=transformation.api.now())
    assert transformation.api.summarize(job) is None  # dbt wrote nothing
    (tmp_path / "target").mkdir()
    results = [
        {"unique_id": "model.a", "status": "success"},
        {"unique_id": "test.b", "status": "fail", "message": "Got 3 results"},
    ]
    path = tmp_path / "target" / "run_results.json"
    path.write_text(json.dumps({"results": results}))
    os.utime(path, (time.time() + 1, time.time() + 1))
    assert transformation.api.summarize(job) == {
        "counts": {"success": 1, "fail": 1},
        "failures": [{"node": "test.b", "status": "fail", "message": "Got 3 results"}],
    }


def test_transformation_rejects_a_second_build(tmp_path, monkeypatch):
    monkeypatch.setattr(transformation.api, "runner", Runner(tmp_path))
    client = TestClient(transformation.api.app)
    transformation.api.runner.start("busy", SLEEP)
    assert client.post("/builds", json={"target": "sample"}).status_code == 409
    assert client.post("/builds", json={"target": "prod"}).status_code == 422
    assert client.get("/builds/nope").status_code == 404
