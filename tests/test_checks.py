import duckdb

from ingestion import checks, odata, runlog


def test_reconcile():
    assert checks.reconcile(10, 10) is None
    assert checks.reconcile(10, 12) == "bronze has 12 rows, API has 10 (+2)"


def test_volume():
    assert checks.volume(0, None) is None  # no history yet
    assert checks.volume(0, 5) is None  # a quiet table
    assert checks.volume(3, 500) is None
    assert checks.volume(0, 500) == "0 rows fetched, usually 500"


def test_ops_records_and_usual_rows(tmp_path):
    db = str(tmp_path / "raw.duckdb")
    runlog.init(db)
    for i, rows in enumerate([5000, 100, 200, 300]):  # the first run is the full load
        run_id = f"run{i}"
        runlog.insert(db, "ingestion_runs", {"run_id": run_id, "mode": "daily", "status": "ok"})
        table = {"run_id": run_id, "table_name": "kns_bill", "status": "ok"}
        table.update(started_at=f"2026-11-0{i + 1}", rows_extracted=rows)
        runlog.insert(db, "ingestion_tables", table)
    with duckdb.connect(db) as con:
        # The first run (the full load) is skipped, the later ones averaged.
        assert checks.usual_rows(con, "kns_bill") == (100 + 200 + 300) / 3


def test_api_row_count_failure_is_a_warning_not_an_error():
    def timing_out(path, params):
        raise odata.EmptyResponse("KNS_PlenumVote: empty response")

    assert checks.api_rows_or_warning(timing_out, "KNS_PlenumVote", None) == (
        None,
        "API row count unavailable (EmptyResponse): not reconciled",
    )
    assert checks.api_rows_or_warning(lambda path, params: {"@odata.count": 7}, "T", None) == (
        7,
        None,
    )
