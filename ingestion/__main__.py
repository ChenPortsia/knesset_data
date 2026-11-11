"""Load Knesset OData tables into the raw DuckDB database, one table at a time.

Run:  python -m ingestion                       # daily: changed rows of all tables
      python -m ingestion --mode weekly         # daily + check for rows deleted in the API
      python -m ingestion --mode sample         # test load: 200 rows per table, separate file
      python -m ingestion KNS_Person KNS_Bill   # only some tables

Writes only to data/raw/raw.duckdb (data/raw/raw_sample.duckdb for samples):
  bronze.*  the tables, every version of every row (SCD2)
  ops.*     one record per run and per table: status, counts, warnings, errors
Logs go to the console and logs/ingestion/<run_id>.log.
Exit code 1 if any table failed, so a scheduler can alert and retry.
"""

import argparse
import logging
import shutil
import sys
from pathlib import Path
from typing import Any

import dlt
import duckdb
from dlt.common.normalizers.naming.snake_case import NamingConvention

from ingestion import checks, runlog
from ingestion.odata import TABLES, Api, Settings, knesset_odata, load_settings, scope

DATA_DIR = Path("data/raw")  # ingestion owns this folder; dbt mounts it read-only

log = logging.getLogger("ingestion")
bronze_name = NamingConvention().normalize_table_identifier  # KNS_PlenumVote -> kns_plenum_vote


def load_table(
    pipeline: dlt.Pipeline,
    db: str,
    source: dlt.sources.DltSource,
    settings: Settings,
    api: Api,
    name: str,
    mode: str,
    run_id: str,
) -> dict[str, Any]:
    """Load one table, run its checks and return its ops record. Never raises."""
    table, scd2, where = bronze_name(name), TABLES[name].incremental, scope(name, settings)
    record: dict[str, Any] = {"table_name": table, "started_at": runlog.now(), "status": "ok"}
    warnings: list[str] = []
    try:
        one_table = source.with_resources(name)
        if mode == "sample":
            one_table.add_limit(settings.sample_pages)
        load_info = pipeline.run(one_table)
        record["load_id"] = load_info.loads_ids[0] if load_info.loads_ids else None
        record["rows_extracted"] = pipeline.last_trace.last_normalize_info.row_counts.get(table, 0)

        with duckdb.connect(db) as con:
            record["bronze_rows"], record["max_updated_at"] = checks.bronze_stats(con, table, scd2)
            if mode != "sample":
                record["api_rows"], warning = checks.api_rows_or_warning(api.json, name, where)
                warnings.append(warning)
                if record["api_rows"] is not None:
                    warnings.append(checks.reconcile(record["api_rows"], record["bronze_rows"]))
                warnings.append(
                    checks.volume(record["rows_extracted"], checks.usual_rows(con, table))
                )
            if mode == "weekly":
                try:
                    deleted = checks.find_deleted(
                        con, api.json, name, table, where, scd2, settings.workers
                    )
                except Exception as error:  # keep last week's list; the data is loaded
                    warnings.append(f"delete check could not run ({type(error).__name__})")
                else:
                    con.execute("DELETE FROM bronze.deleted_ids WHERE table_name = ?", [table])
                    con.executemany(
                        "INSERT INTO bronze.deleted_ids VALUES (?, ?, ?, ?)",
                        [(table, i, record["started_at"], run_id) for i in sorted(deleted)],
                    )
                    record["deleted_rows"] = len(deleted)
                    if deleted:
                        warnings.append(f"{len(deleted)} rows deleted in the API")
    except Exception as error:
        log.exception("%s failed", name)
        record.update(status="failed", error=str(error)[:4000])

    warnings = [w for w in warnings if w]
    if warnings and record["status"] == "ok":
        record["status"] = "warn"
    record.update(warnings="; ".join(warnings) or None, finished_at=runlog.now())
    seconds = (record["finished_at"] - record["started_at"]).total_seconds()
    log.info(
        "%-24s %-6s %8s rows fetched, %8s in bronze, %5.0fs %s",
        name, record["status"], record.get("rows_extracted"), record.get("bronze_rows"),
        seconds, record["warnings"] or "",
    )  # fmt: skip
    return record


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Load Knesset OData tables into data/raw/raw.duckdb"
    )
    parser.add_argument("tables", nargs="*", help="table names, default: all")
    parser.add_argument("--mode", choices=["daily", "weekly", "sample"], default="daily")
    parser.add_argument("--run-id", help="set by the API; default: the start time")
    args = parser.parse_args()
    if unknown := set(args.tables) - set(TABLES):
        parser.error(f"unknown tables: {sorted(unknown)}")

    name = "knesset_sample" if args.mode == "sample" else "knesset"
    db, pipelines_dir = (
        str(DATA_DIR / f"{name.replace('knesset', 'raw')}.duckdb"),
        DATA_DIR / ".dlt",
    )
    if args.mode == "sample":  # a sample starts from scratch, so it never affects the real load
        Path(db).unlink(missing_ok=True)
        shutil.rmtree(pipelines_dir / name, ignore_errors=True)

    run_id = args.run_id or runlog.new_run_id()
    log_file = runlog.setup_logging(run_id)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    runlog.init(db)
    run: dict[str, Any] = {
        "run_id": run_id,
        "mode": args.mode,
        "started_at": runlog.now(),
        "log_file": str(log_file),
    }
    log.info("run %s, mode %s, into %s", run_id, args.mode, db)

    pipeline = dlt.pipeline(
        pipeline_name=name,
        pipelines_dir=str(pipelines_dir),
        destination=dlt.destinations.duckdb(db),
        dataset_name="bronze",
    )
    settings = load_settings()
    api = Api(settings)
    workers = 1 if args.mode == "sample" else settings.workers
    source = knesset_odata(settings, api, api.metadata(), workers, args.tables or list(TABLES))
    records = [
        load_table(pipeline, db, source, settings, api, table, args.mode, run_id)
        for table in args.tables or TABLES
    ]
    for record in records:
        runlog.insert(db, "ingestion_tables", {"run_id": run_id, **record})

    counts = {s: sum(r["status"] == s for r in records) for s in ("ok", "warn", "failed")}
    status = "failed" if counts["failed"] else "warn" if counts["warn"] else "ok"
    run.update(
        finished_at=runlog.now(), status=status,
        tables_ok=counts["ok"], tables_warn=counts["warn"], tables_failed=counts["failed"],
    )  # fmt: skip
    runlog.insert(db, "ingestion_runs", run)
    log.info("run %s finished: %s (%s), log: %s", run_id, status, counts, log_file)
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
