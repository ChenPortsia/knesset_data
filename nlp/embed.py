"""Embed the chunks: turn each chunk's text into a vector, for search by meaning.

Two models to choose between (make embed-benchmark times both on your machine):
    e5-large   the model the context layer uses: best at meaning, slow without a GPU
    potion     a static model: no neural network at run time, so thousands of chunks a
               second on any machine; weaker at meaning
One model's vectors can't be compared with another's, so rag.embeddings holds one model at
a time; embedding with a different model starts over.
"""

import time
from typing import Any

import duckdb

# name -> fastembed model, the prefix it expects before a text to index and before a question
MODELS = {
    "e5-large": ("intfloat/multilingual-e5-large", "passage: ", "query: "),
    "potion": ("minishlab/potion-multilingual-128M", "", ""),
}
DEFAULT = "e5-large"
BATCH = 256  # chunks embedded and saved at a time, so a stopped run keeps its work


def load(model: str) -> Any:
    from fastembed import TextEmbedding  # here, not at the top: slow to import

    return TextEmbedding(MODELS[model][0])


def vectors(encoder: Any, model: str, texts: list[str]) -> list[list[float]]:
    prefix = MODELS[model][1]
    return [v.tolist() for v in encoder.embed([prefix + text for text in texts])]


def embed_new(con: duckdb.DuckDBPyConnection, model: str = DEFAULT) -> tuple[int, int]:
    """Embed the chunks that have no vector yet. Returns (embedded now, embedded in all)."""
    con.execute("CREATE SCHEMA IF NOT EXISTS rag")
    build = (model, MODELS[model][0], MODELS[model][2])
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS rag.build (
            model VARCHAR, embedding_model VARCHAR, question_prefix VARCHAR
        )
        """
    )
    if con.execute("SELECT * FROM rag.build").fetchone() != build:
        con.execute("DROP TABLE IF EXISTS rag.embeddings")  # another model's vectors
        con.execute("DELETE FROM rag.build")
        con.execute("INSERT INTO rag.build VALUES (?, ?, ?)", build)
    encoder = load(model)
    size = len(vectors(encoder, model, ["x"])[0])
    con.execute(
        f"""
        CREATE TABLE IF NOT EXISTS rag.embeddings (
            chunk_id VARCHAR PRIMARY KEY, text_hash VARCHAR, embedding FLOAT[{size}]
        )
        """
    )
    # A chunk whose text changed gets a new vector; a chunk that is gone loses its vector
    con.execute(
        """
        DELETE FROM rag.embeddings WHERE (chunk_id, text_hash) NOT IN (
            SELECT (chunk_id, MD5(chunk_text)) FROM rag.chunks
        )
        """
    )
    todo = con.execute(
        """
        SELECT chunk_id, chunk_text FROM rag.chunks
        WHERE chunk_id NOT IN (SELECT chunk_id FROM rag.embeddings)
        ORDER BY chunk_id
        """
    ).fetchall()
    for start in range(0, len(todo), BATCH):
        batch = todo[start : start + BATCH]
        embedded = vectors(encoder, model, [text for _, text in batch])
        con.executemany(
            "INSERT INTO rag.embeddings VALUES (?, MD5(?), ?)",
            [(id_, text, v) for (id_, text), v in zip(batch, embedded, strict=True)],
        )
        if (start // BATCH) % 10 == 0:
            print(f"  {start + len(batch):,} of {len(todo):,}", flush=True)
    return len(todo), con.execute("SELECT COUNT(*) FROM rag.embeddings").fetchone()[0]


def benchmark(con: duckdb.DuckDBPyConnection, sample: int) -> None:
    """Time each model on the same chunks and say how long every chunk would take."""
    texts = [
        r[0]
        for r in con.execute(
            # ordered by a hash of the id: the same mixed sample on every run
            "SELECT chunk_text FROM rag.chunks ORDER BY MD5(chunk_id) LIMIT ?",
            [sample],
        ).fetchall()
    ]
    total = con.execute("SELECT COUNT(*) FROM rag.chunks").fetchone()[0]
    print(f"{len(texts)} chunks timed; {total:,} chunks loaded\n")
    print(
        f"{'model':10} {'size':>5} {'chunks/s':>9} {'all loaded chunks':>18} {'500,000 chunks':>15}"
    )
    for model in MODELS:
        encoder = load(model)
        vectors(encoder, model, texts[:4])  # warm up: the first call loads the model
        started = time.time()
        size = len(vectors(encoder, model, texts)[0])
        rate = len(texts) / (time.time() - started)
        print(
            f"{model:10} {size:>5} {rate:>9.1f} {minutes(total / rate):>18} "
            f"{minutes(500_000 / rate):>15}"
        )


def minutes(seconds: float) -> str:
    return f"{seconds / 60:.0f} min" if seconds < 7200 else f"{seconds / 3600:.1f} hours"
