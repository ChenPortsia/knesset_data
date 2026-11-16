"""Load committee protocols (ivrit-ai/knesset-committees on Hugging Face) into bronze.

Run:  python -m ingestion.protocols --committee "ועדת הכספים" --year 2024    a slice
      python -m ingestion.protocols --limit 20                              a few, to try
      python -m ingestion.protocols                                         every session

A separate pipeline from OData: its own dlt pipeline, run record and log. Each session is a
folder named by its committee_session_id; of its 14 files we take three small text files:
    raw.protocol.txt        what was said, as one text
    speakers.txt            speaker id and name, as written in the protocol
    speakers.segments.txt   who spoke which part: speaker id, start and end character

Writes to data/raw/raw.duckdb:
    bronze.protocol_manifest   the dataset's list of sessions (replaced each run)
    bronze.protocol_text       one row per session
    bronze.protocol_speakers   one row per session and speaker
    bronze.protocol_segments   one row per speaker turn
A protocol never changes, so a run loads only sessions that are not in bronze yet.
Needs a Hugging Face token whose account accepted the dataset's terms, in
ingestion/.dlt/secrets.toml (never committed):
    [sources.knesset_protocols]
    hf_token = "hf_..."
or in the HF_TOKEN environment variable.
"""

import argparse
import csv
import io
import logging
import os
import sys
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from itertools import batched
from pathlib import Path
from typing import Any

import dlt
import duckdb
from dlt.sources.helpers.requests import Client

from ingestion import runlog
from ingestion.__main__ import DATA_DIR

log = logging.getLogger("ingestion.protocols")

FILES = ("raw.protocol.txt", "speakers.txt", "speakers.segments.txt")
MANIFEST_COLUMNS = ("session_id", "session_date", "knesset_num", "committee_name", "words_count")
TABLES = ("protocol_text", "protocol_speakers", "protocol_segments")

Get = Callable[[str], str]


def token_help() -> str:
    """Why no token was found: says what the secrets file holds, by name only."""
    path = Path(__file__).parent / ".dlt" / "secrets.toml"
    wanted = '[sources.knesset_protocols]\nhf_token = "hf_..."'
    if not path.exists():
        return f"No Hugging Face token. Create {path} with:\n{wanted}"
    found = [
        line.split("=")[0].strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    return (
        f"No Hugging Face token. {path} exists but has no hf_token under "
        f"[sources.knesset_protocols].\nIt has these lines (names only): {found}\n"
        f"It should have exactly:\n{wanted}"
    )


def make_get(base_url: str) -> Get:
    """Download one file of the dataset as text, with retries."""
    session = Client(request_timeout=120, request_max_attempts=6).session
    token = dlt.secrets.get("sources.knesset_protocols.hf_token") or os.environ.get("HF_TOKEN")
    if not token:
        raise SystemExit(token_help())
    session.headers["Authorization"] = f"Bearer {token}"

    def get(path: str) -> str:
        response = session.get(base_url + path)
        response.raise_for_status()
        return response.content.decode("utf-8")

    return get


def read_manifest(text: str) -> list[dict[str, Any]]:
    """The dataset's list of sessions, with the columns we keep."""
    return [
        {column: row[column] for column in MANIFEST_COLUMNS}
        | {
            "session_id": int(row["session_id"]),
            "words_count": int(float(row["words_count"])) if row["words_count"] else None,
        }
        for row in csv.DictReader(io.StringIO(text))
    ]


def parse_session(session_id: int, files: dict[str, str]) -> dict[str, list[dict[str, Any]]]:
    """One session's three files as rows of the three tables."""
    text = files["raw.protocol.txt"]
    speakers = [line.split("\t", 1) for line in files["speakers.txt"].splitlines() if line]
    segments = [line.split("\t") for line in files["speakers.segments.txt"].splitlines() if line]
    return {
        "protocol_text": [{"session_id": session_id, "text": text, "characters": len(text)}],
        "protocol_speakers": [
            {"session_id": session_id, "speaker_id": int(id_), "speaker_name": name.strip()}
            for id_, name in speakers
        ],
        "protocol_segments": [
            {
                "session_id": session_id,
                "segment_index": index,
                "speaker_id": int(id_),
                "start_char": int(start),
                "end_char": int(end),
            }
            for index, (id_, start, end) in enumerate(segments)
        ],
    }


def fetch_session(get: Get, session_id: int) -> dict[str, list[dict[str, Any]]] | None:
    """Download and parse one session; None (and a log line) if it can't be read."""
    try:
        return parse_session(session_id, {name: get(f"{session_id}/{name}") for name in FILES})
    except Exception as error:
        log.warning("session %s skipped: %s: %s", session_id, type(error).__name__, error)
        return None


@dlt.resource(name="protocols", write_disposition="append")
def protocols(get: Get, session_ids: tuple[int, ...], workers: int) -> Iterator[Any]:
    """The rows of a batch of sessions, each sent to its own table."""
    with ThreadPoolExecutor(workers) as pool:
        for session in pool.map(lambda id_: fetch_session(get, id_), session_ids):
            for table, rows in (session or {}).items():
                yield dlt.mark.with_table_name(rows, table)


def wanted(
    con: duckdb.DuckDBPyConnection, manifest: list[dict[str, Any]], committee: str | None,
    year: int | None, limit: int | None,
) -> tuple[list[int], dict[str, int]]:  # fmt: skip
    """Session ids to load now, and the counts that explain the choice."""
    known = {r[0] for r in con.execute("SELECT id FROM bronze.kns_committee_session").fetchall()}
    tables = {r[0] for r in con.execute("SHOW TABLES FROM bronze").fetchall()}
    loaded = (
        {r[0] for r in con.execute("SELECT session_id FROM bronze.protocol_text").fetchall()}
        if "protocol_text" in tables
        else set()
    )
    chosen = [
        row["session_id"]
        for row in manifest
        if (committee is None or row["committee_name"] == committee)
        and (year is None or row["session_date"].startswith(str(year)))
    ]
    todo = sorted(set(chosen) & known - loaded)[:limit]
    return todo, {
        "in_dataset": len(manifest),
        "chosen": len(chosen),
        "unknown_session": len(set(chosen) - known),
        "already_loaded": len(set(chosen) & loaded),
        "to_load": len(todo),
    }


def check(con: duckdb.DuckDBPyConnection, asked: int) -> tuple[dict[str, int], list[str]]:
    """Row counts in bronze, and what looks wrong."""
    counts = {
        table: con.execute(f"SELECT COUNT(*) FROM bronze.{table}").fetchone()[0] for table in TABLES
    }
    this_run = con.execute(
        """
        SELECT COUNT(*) FROM bronze.protocol_text
        WHERE _dlt_load_id IN (SELECT load_id FROM bronze._dlt_loads ORDER BY inserted_at DESC
                               LIMIT ?)
        """,
        [max(1, -(-asked // dlt.config["sources.knesset_protocols.batch_sessions"]))],
    ).fetchone()[0]
    empty, beyond, no_speaker = con.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM bronze.protocol_text WHERE characters = 0),
            (SELECT COUNT(DISTINCT s.session_id) FROM bronze.protocol_segments AS s
             INNER JOIN bronze.protocol_text AS t USING (session_id)
             WHERE s.end_char > t.characters),
            (SELECT COUNT(*) FROM bronze.protocol_segments AS s
             ANTI JOIN bronze.protocol_speakers AS p USING (session_id, speaker_id))
        """
    ).fetchone()
    warnings = [
        f"{asked - this_run} of {asked} sessions could not be loaded" if this_run < asked else "",
        f"{empty} sessions have no text" if empty else "",
        f"{beyond} sessions have segments past the end of their text" if beyond else "",
        f"{no_speaker} segments have no speaker row" if no_speaker else "",
    ]
    return counts, [w for w in warnings if w]


def main() -> int:
    parser = argparse.ArgumentParser(description="Load committee protocols into bronze")
    parser.add_argument("--committee", help="only this committee name, as in the dataset")
    parser.add_argument("--year", type=int, help="only sessions of this year")
    parser.add_argument("--limit", type=int, help="at most this many sessions")
    args = parser.parse_args()

    db = str(DATA_DIR / "raw.duckdb")
    run_id = runlog.new_run_id()
    log_file = runlog.setup_logging(run_id)
    runlog.init(db)
    run = {
        "run_id": run_id, "mode": "protocols", "started_at": runlog.now(),
        "log_file": str(log_file),
    }  # fmt: skip
    settings = {
        key: dlt.config[f"sources.knesset_protocols.{key}"]
        for key in ("base_url", "workers", "batch_sessions")
    }
    get = make_get(settings["base_url"])
    pipeline = dlt.pipeline(
        pipeline_name="knesset_protocols",
        pipelines_dir=str(DATA_DIR / ".dlt"),
        destination=dlt.destinations.duckdb(db),
        dataset_name="bronze",
    )
    record: dict[str, Any] = {
        "table_name": "protocols", "started_at": runlog.now(), "status": "ok"
    }  # fmt: skip
    try:
        manifest = read_manifest(get("manifest.csv"))
        pipeline.run(manifest, table_name="protocol_manifest", write_disposition="replace")
        with duckdb.connect(db, read_only=True) as con:
            todo, counts = wanted(con, manifest, args.committee, args.year, args.limit)
        log.info("run %s: %s", run_id, counts)
        for done, batch in enumerate(batched(todo, settings["batch_sessions"])):
            pipeline.run(protocols(get, batch, settings["workers"]))
            log.info("loaded %s of %s sessions", done * len(batch) + len(batch), len(todo))
        with duckdb.connect(db, read_only=True) as con:
            rows, warnings = check(con, len(todo)) if todo else ({}, [])
        record.update(
            rows_extracted=len(todo), bronze_rows=rows.get("protocol_text"),
            api_rows=counts["chosen"], warnings="; ".join(warnings) or None,
            status="warn" if warnings else "ok",
        )  # fmt: skip
        log.info("bronze now has %s; warnings: %s", rows, warnings or "none")
    except Exception as error:
        log.exception("protocols failed")
        record.update(status="failed", error=str(error)[:4000])

    record["finished_at"] = runlog.now()
    runlog.insert(db, "ingestion_tables", {"run_id": run_id, **record})
    status = record["status"]
    run.update(
        finished_at=runlog.now(), status=status, tables_ok=int(status == "ok"),
        tables_warn=int(status == "warn"), tables_failed=int(status == "failed"),
    )  # fmt: skip
    runlog.insert(db, "ingestion_runs", run)
    log.info("run %s finished: %s, log: %s", run_id, status, log_file)
    return 1 if status == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
