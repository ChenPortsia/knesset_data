"""Load the Knesset's own protocol documents into bronze, paragraph by paragraph.

Run:  python -m ingestion.documents committee --knesset 25 --year 2024 --committee-id 4198
      python -m ingestion.documents plenum --limit 20
      python -m ingestion.documents committee              every committee protocol

The OData tables KNS_DocumentCommitteeSession / KNS_DocumentPlenumSession (loaded by
`make ingest`) link each session to its files. This pipeline takes each session's protocol
(a Word file), downloads it once, and stores its paragraphs as they are, each with the name
of its paragraph style. The Knesset's styles say who speaks (יור, דובר, אורח), what the
subject is (נושא) and where the votes are (הצבעה_מספר); dbt turns them into speaker turns,
so changing how turns are cut never needs a new download.

Writes to data/raw/raw.duckdb:
    bronze.protocol_documents    one row per downloaded file: session, link, size, counts
    bronze.protocol_paragraphs   one row per paragraph: its place, style and text
A document is loaded once: a run takes only documents that are not in bronze yet.
"""

import argparse
import io
import logging
import sys
import zipfile
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from itertools import batched
from typing import Any
from xml.etree import ElementTree

import dlt
import duckdb

from ingestion import runlog
from ingestion.__main__ import DATA_DIR
from ingestion.odata import Api, load_settings

log = logging.getLogger("ingestion.documents")

# kind -> (document link table, its session column, session table, the protocol's label)
KINDS = {
    "committee": (
        "kns_document_committee_session", "committee_session_id", "kns_committee_session",
        "פרוטוקול ועדה",
    ),
    "plenum": (
        "kns_document_plenum_session", "plenum_session_id", "kns_plenum_session", "דברי הכנסת",
    ),
}  # fmt: skip
WORD = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
# The Knesset's paragraph styles that open a speaker's turn: the chair, an MK or minister,
# a guest, a speaker continuing, a call from the floor (see docs/milestone_4_plan.md)
SPEAKER_STYLES = ("יור", "דובר", "אורח", "דובר-המשך", "קריאות")

Get = Callable[[str], bytes]


def read_paragraphs(content: bytes) -> list[tuple[str | None, str]] | None:
    """(style, text) of every non-empty paragraph of a .docx file, in order.
    None if the file is not a .docx (a few old files are in Word's earlier format)."""
    if not zipfile.is_zipfile(io.BytesIO(content)):
        return None
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
        styles = ElementTree.fromstring(archive.read("word/styles.xml"))
    # A paragraph points to its style by an id that differs from file to file (the chair is
    # af6 in one, af7 in another); the style's name is the same in every file
    names = {
        style.get(f"{WORD}styleId"): style.find(f"{WORD}name").get(f"{WORD}val")
        for style in styles.iter(f"{WORD}style")
        if style.find(f"{WORD}name") is not None
    }
    paragraphs = []
    for paragraph in root.iter(f"{WORD}p"):
        style = paragraph.find(f"{WORD}pPr/{WORD}pStyle")
        pieces = [
            node.text or "" if node.tag == f"{WORD}t" else " "  # a tab or a line break
            for node in paragraph.iter()
            if node.tag in (f"{WORD}t", f"{WORD}tab", f"{WORD}br")
        ]
        text = "".join(pieces).strip()
        if text:
            style_id = style.get(f"{WORD}val") if style is not None else None
            paragraphs.append((names.get(style_id, style_id), text))
    return paragraphs


def to_rows(document: dict[str, Any], content: bytes) -> dict[str, list[dict[str, Any]]]:
    """A downloaded document as rows of the two tables."""
    paragraphs = read_paragraphs(content)
    summary = document | {
        "bytes": len(content),
        "is_docx": paragraphs is not None,
        "paragraphs": len(paragraphs or []),
        "speaker_paragraphs": sum(style in SPEAKER_STYLES for style, _ in paragraphs or []),
    }
    return {
        "protocol_documents": [summary],
        "protocol_paragraphs": [
            {
                "document_id": document["document_id"],
                "paragraph_index": index,
                "style": style,
                "paragraph_text": text,
            }
            for index, (style, text) in enumerate(paragraphs or [])
        ],
    }


def fetch(get: Get, document: dict[str, Any]) -> dict[str, list[dict[str, Any]]] | None:
    """Download and read one document; None (and a log line) if it can't be downloaded."""
    try:
        return to_rows(document, get(document["file_path"].replace("\\", "/")))
    except Exception as error:
        log.warning(
            "document %s skipped: %s: %s", document["document_id"], type(error).__name__, error
        )
        return None


@dlt.resource(name="documents", write_disposition="append")
def documents(get: Get, batch: tuple[dict[str, Any], ...], workers: int) -> Iterator[Any]:
    """The rows of a batch of documents, each sent to its own table."""
    with ThreadPoolExecutor(workers) as pool:
        for rows in pool.map(lambda document: fetch(get, document), batch):
            for table, table_rows in (rows or {}).items():
                yield dlt.mark.with_table_name(table_rows, table)


def wanted(
    con: duckdb.DuckDBPyConnection, kind: str, knesset: int | None = None,
    year: int | None = None, committee_id: int | None = None, limit: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:  # fmt: skip
    """The protocol documents to download now, and the counts that explain the choice.

    One document per session: its newest protocol in Word format, for sessions in our scope.
    """
    links, session_column, sessions, label = KINDS[kind]
    tables = {r[0] for r in con.execute("SHOW TABLES FROM bronze").fetchall()}
    loaded = "protocol_documents" in tables
    committee = "AND s.committee_id = $committee_id" if kind == "committee" else ""
    rows = con.execute(
        f"""
        SELECT
            d.id AS document_id, d.{session_column} AS session_id, d.file_path,
            {"d.id IN (SELECT document_id FROM bronze.protocol_documents)" if loaded else "FALSE"}
                AS is_loaded
        FROM bronze.{links} AS d
        INNER JOIN bronze.{sessions} AS s
            ON d.{session_column} = s.id AND s._dlt_valid_to IS NULL
        WHERE d._dlt_valid_to IS NULL
          AND d.group_type_desc = $label AND d.application_desc = 'DOC'
          AND ($knesset IS NULL OR s.knesset_num = $knesset)
          AND ($year IS NULL OR YEAR(s.start_date) = $year)
          {committee if committee_id is not None else ""}
        QUALIFY ROW_NUMBER() OVER (PARTITION BY d.{session_column} ORDER BY d.id DESC) = 1
        ORDER BY d.id
        """,
        {"label": label, "knesset": knesset, "year": year}
        | ({"committee_id": committee_id} if kind == "committee" and committee_id else {}),
    ).fetchall()
    todo = [
        {"document_id": id_, "session_id": session, "kind": kind, "file_path": path}
        for id_, session, path, is_loaded in rows
        if not is_loaded
    ][:limit]
    return todo, {
        "sessions_with_a_protocol": len(rows),
        "already_loaded": sum(is_loaded for *_, is_loaded in rows),
        "to_load": len(todo),
    }


def check(con: duckdb.DuckDBPyConnection, ids: list[int]) -> tuple[dict[str, int], list[str]]:
    """What this run loaded, and what looks wrong in it."""
    loaded, not_docx, no_speakers = con.execute(
        """
        SELECT COUNT(*), COUNT(*) FILTER (WHERE NOT is_docx),
            COUNT(*) FILTER (WHERE is_docx AND speaker_paragraphs = 0)
        FROM bronze.protocol_documents WHERE document_id IN ?
        """,
        [ids],
    ).fetchone()
    # A style that no earlier document had may be new formatting to learn (nothing to
    # compare with on the first load)
    new_styles = con.execute(
        """
        SELECT style, COUNT(*) FROM bronze.protocol_paragraphs
        WHERE document_id IN $ids AND style IS NOT NULL
          AND EXISTS (SELECT 1 FROM bronze.protocol_documents WHERE document_id NOT IN $ids)
          AND style NOT IN (SELECT style FROM bronze.protocol_paragraphs
                            WHERE document_id NOT IN $ids AND style IS NOT NULL)
        GROUP BY style ORDER BY 2 DESC LIMIT 10
        """,
        {"ids": ids},
    ).fetchall()
    warnings = [
        f"{len(ids) - loaded} of {len(ids)} documents could not be downloaded"
        if loaded < len(ids) else "",
        f"{not_docx} documents are not .docx files and were not read" if not_docx else "",
        f"{no_speakers} documents have no speaker paragraphs" if no_speakers else "",
        f"paragraph styles not seen before: {dict(new_styles)}" if new_styles else "",
    ]  # fmt: skip
    return {"documents": loaded}, [w for w in warnings if w]


def run(kind: str, get: Get | None = None, db: str | None = None, **filters: Any) -> dict[str, Any]:
    """Load the documents that are not in bronze yet; returns the run's table record."""
    db = db or str(DATA_DIR / "raw.duckdb")
    settings = {
        key: dlt.config[f"sources.knesset_documents.{key}"]
        for key in ("workers", "batch_documents")
    }
    if get is None:
        session = Api(load_settings()).session  # the same retries and backoff as the API
        get = lambda url: _content(session.get(url))  # noqa: E731
    pipeline = dlt.pipeline(
        pipeline_name="knesset_documents",
        pipelines_dir=str(DATA_DIR / ".dlt"),
        destination=dlt.destinations.duckdb(db),
        dataset_name="bronze",
    )
    record: dict[str, Any] = {
        "table_name": f"protocol_documents ({kind})", "started_at": runlog.now(), "status": "ok",
    }  # fmt: skip
    try:
        with duckdb.connect(db, read_only=True) as con:
            todo, counts = wanted(con, kind, **filters)
        log.info("%s protocols: %s", kind, counts)
        for done, batch in enumerate(batched(todo, settings["batch_documents"]), start=1):
            pipeline.run(documents(get, batch, settings["workers"]))
            log.info("loaded %s of %s documents",
                     min(done * settings["batch_documents"], len(todo)), len(todo))  # fmt: skip
        with duckdb.connect(db, read_only=True) as con:
            ids = [d["document_id"] for d in todo]
            rows, warnings = check(con, ids) if todo else ({}, [])
        record.update(
            rows_extracted=len(todo), bronze_rows=rows.get("documents"),
            api_rows=counts["sessions_with_a_protocol"], warnings="; ".join(warnings) or None,
            status="warn" if warnings else "ok",
        )  # fmt: skip
        log.info("loaded %s; warnings: %s", rows, warnings or "none")
    except Exception as error:
        log.exception("documents failed")
        record.update(status="failed", error=str(error)[:4000])
    record["finished_at"] = runlog.now()
    return record


def _content(response: Any) -> bytes:
    response.raise_for_status()
    return response.content


def main() -> int:
    parser = argparse.ArgumentParser(description="Load Knesset protocol documents into bronze")
    parser.add_argument("kind", choices=list(KINDS))
    parser.add_argument("--knesset", type=int, help="only sessions of this Knesset")
    parser.add_argument("--year", type=int, help="only sessions of this year")
    parser.add_argument("--committee-id", type=int, help="only this committee (committee kind)")
    parser.add_argument("--limit", type=int, help="at most this many documents")
    args = parser.parse_args()

    db = str(DATA_DIR / "raw.duckdb")
    run_id = runlog.new_run_id()
    log_file = runlog.setup_logging(run_id)
    runlog.init(db)
    started = runlog.now()
    record = run(
        args.kind, knesset=args.knesset, year=args.year, committee_id=args.committee_id,
        limit=args.limit,
    )  # fmt: skip
    runlog.insert(db, "ingestion_tables", {"run_id": run_id, **record})
    status = record["status"]
    runlog.insert(
        db, "ingestion_runs",
        {
            "run_id": run_id, "mode": f"documents-{args.kind}", "started_at": started,
            "finished_at": runlog.now(), "status": status, "tables_ok": int(status == "ok"),
            "tables_warn": int(status == "warn"), "tables_failed": int(status == "failed"),
            "log_file": str(log_file),
        },
    )  # fmt: skip
    log.info("run %s finished: %s, log: %s", run_id, status, log_file)
    return 1 if status == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
