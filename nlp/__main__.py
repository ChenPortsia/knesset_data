"""The text batch: chunk the committee turns, embed the chunks, time the models.

    python -m nlp chunk                 gold.fct_turn -> rag.chunks              (make chunks)
    python -m nlp embed                 embed chunks not embedded yet            (make embed)
    python -m nlp benchmark             time each model on a sample of chunks

Reads and writes data/warehouse/warehouse.duckdb, after `make dbt`. The `rag` schema:
    rag.chunks       one row per chunk: its text, session, committee, date, speakers
    rag.embeddings   one row per embedded chunk: the vector
    rag.build        which model the vectors come from
"""

import argparse
import sys
import time
from itertools import groupby
from pathlib import Path

import duckdb

from nlp import embed
from nlp.chunk import Turn, chunk_session, to_row

WAREHOUSE = Path(__file__).resolve().parents[1] / "data" / "warehouse" / "warehouse.duckdb"

TURNS = """
    SELECT
        turns.committee_session_id, turns.committee_id, turns.knesset_num,
        CAST(turns.session_date AS VARCHAR) AS session_date, committees.committee_name,
        turns.turn_index, COALESCE(turns.speaker_name, 'דובר לא ידוע') AS speaker_name,
        turns.person_id, turns.turn_text
    FROM gold.fct_turn AS turns
    INNER JOIN gold.dim_committee AS committees ON turns.committee_id = committees.committee_id
    ORDER BY turns.committee_session_id, turns.turn_index
"""
CHUNKS_DDL = """
    CREATE SCHEMA IF NOT EXISTS rag;
    CREATE OR REPLACE TABLE rag.chunks (
        chunk_id VARCHAR PRIMARY KEY, committee_session_id INTEGER, committee_id INTEGER,
        knesset_num INTEGER, session_date DATE, first_turn INTEGER, last_turn INTEGER,
        speakers VARCHAR[], person_ids INTEGER[], words INTEGER, chunk_text VARCHAR
    );
"""


def chunk(con: duckdb.DuckDBPyConnection) -> None:
    """Rebuild rag.chunks from gold.fct_turn."""
    cursor = con.execute(TURNS)
    columns = [c[0] for c in cursor.description]
    rows = []
    for _, group in groupby(cursor.fetchall(), key=lambda r: r[0]):
        turns = [dict(zip(columns, r, strict=True)) for r in group]
        session_turns = [
            Turn(t["turn_index"], t["speaker_name"], t["person_id"], t["turn_text"]) for t in turns
        ]
        rows += [to_row(turns[0], c) for c in chunk_session(session_turns)]
    con.execute(CHUNKS_DDL)
    con.executemany(
        "INSERT INTO rag.chunks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [list(row.values()) for row in rows],
    )
    sessions, words, longest = con.execute(
        "SELECT COUNT(DISTINCT committee_session_id), ROUND(AVG(words)), MAX(words) FROM rag.chunks"
    ).fetchone()
    print(f"{len(rows):,} chunks from {sessions:,} sessions; {words:.0f} words on average, "
          f"{longest} at most")  # fmt: skip


def main() -> int:
    parser = argparse.ArgumentParser(description="Chunk and embed the committee protocols")
    parser.add_argument("command", choices=["chunk", "embed", "benchmark"])
    parser.add_argument("--model", default=embed.DEFAULT, choices=list(embed.MODELS))
    parser.add_argument("--sample", type=int, default=200, help="chunks to time in a benchmark")
    args = parser.parse_args()

    with duckdb.connect(str(WAREHOUSE)) as con:
        if args.command == "chunk":
            chunk(con)
        elif args.command == "embed":
            started = time.time()
            done, total = embed.embed_new(con, args.model)
            print(f"embedded {done:,} chunks with {args.model} in {time.time() - started:.0f}s; "
                  f"{total:,} chunks have vectors")  # fmt: skip
        else:
            embed.benchmark(con, args.sample)
    return 0


if __name__ == "__main__":
    sys.exit(main())
