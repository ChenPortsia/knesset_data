"""Embed the chunks: turn each chunk's text into a vector, for search by meaning.

Two models to choose between (make embed-benchmark times both on your machine):
    e5-large   the model the context layer uses: best at meaning, slow without a GPU
    potion     a static model: no neural network at run time, so thousands of chunks a
               second on any machine; weaker at meaning
One model's vectors can't be compared with another's, so rag.embeddings holds one model at
a time; embedding with a different model starts over.
"""

import time
from collections.abc import Callable

import duckdb

# name -> model on Hugging Face, the prefix it expects before a text to index and before a
# question, and how it is run:
#   cpu     fastembed on the processor
#   torch   PyTorch, which uses the Mac's GPU (Metal) or an NVIDIA card when there is one;
#           needs `uv sync --group gpu`
# The two e5-large rows are one model, so their vectors are interchangeable.
# (Apple's CoreML through fastembed was tried on an M1 Max: it supports only part of the
# model, ran out of memory and was killed, so it is not offered.)
# The last value is how much more a keyword match should count than a match by meaning when
# the two rankings are merged: 1 for a model that is good at meaning, more for a weak one
# (measured on knesset-agent's text test). It is stored with the vectors for the search to use.
MODELS = {
    "e5-large": ("intfloat/multilingual-e5-large", "passage: ", "query: ", "cpu", 1),
    "e5-large-torch": ("intfloat/multilingual-e5-large", "passage: ", "query: ", "torch", 1),
    "potion": ("minishlab/potion-multilingual-128M", "", "", "cpu", 4),
}
DEFAULT = "e5-large"
BATCH = 256  # chunks embedded and saved at a time, so a stopped run keeps its work

Encoder = Callable[[list[str]], list[list[float]]]


def load(model: str) -> Encoder:
    """A function that embeds texts with the model, on the backend its row names."""
    name, prefix, _, backend, _ = MODELS[model]
    if backend == "torch":
        from sentence_transformers import SentenceTransformer

        encoder = SentenceTransformer(name)  # picks the GPU itself when there is one
        return lambda texts: encoder.encode(
            [prefix + text for text in texts], normalize_embeddings=True, batch_size=32
        ).tolist()

    from fastembed import TextEmbedding  # here, not at the top: slow to import

    embedder = TextEmbedding(name)
    return lambda texts: [v.tolist() for v in embedder.embed([prefix + text for text in texts])]


def embed_new(con: duckdb.DuckDBPyConnection, model: str = DEFAULT) -> tuple[int, int]:
    """Embed the chunks that have no vector yet. Returns (embedded now, embedded in all)."""
    con.execute("CREATE SCHEMA IF NOT EXISTS rag")
    name, _, question_prefix, _, keyword_weight = MODELS[model]
    build = (name, question_prefix, keyword_weight)
    try:
        same_model = con.execute("SELECT * FROM rag.build").fetchone() == build
    except duckdb.Error:  # no rag.build yet, or one from an older layout
        same_model = False
    if not same_model:
        con.execute("DROP TABLE IF EXISTS rag.embeddings")  # another model's vectors
        con.execute(
            """
            CREATE OR REPLACE TABLE rag.build AS
            SELECT ? AS embedding_model, ? AS question_prefix, ? AS keyword_weight
            """,
            build,
        )
    encode = load(model)
    size = len(encode(["x"])[0])
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
        embedded = encode([text for _, text in batch])
        con.executemany(
            "INSERT INTO rag.embeddings VALUES (?, MD5(?), ?)",
            [(id_, text, v) for (id_, text), v in zip(batch, embedded, strict=True)],
        )
        if (start // BATCH) % 10 == 0:
            print(f"  {start + len(batch):,} of {len(todo):,}", flush=True)
    return len(todo), con.execute("SELECT COUNT(*) FROM rag.embeddings").fetchone()[0]


def benchmark(con: duckdb.DuckDBPyConnection, sample: int, models: list[str]) -> None:
    """Time each model on the same chunks and say how long every chunk would take.

    A row that can't run here (no GPU, a package not installed) says why and is skipped.
    'same as cpu' compares a GPU run's vectors with the processor's: 1.000 means identical.
    """
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
        f"{'model':16} {'size':>5} {'chunks/s':>9} {'loaded chunks':>14} {'500,000':>10} "
        "same as cpu"
    )
    reference: dict[str, list[list[float]]] = {}  # the cpu vectors of each Hugging Face model
    for model in models:
        name, _, _, backend, _ = MODELS[model]
        try:
            encode = load(model)
            encode(texts[:4])  # warm up: the first call loads the model
            started = time.time()
            embedded = encode(texts)
        except Exception as error:
            print(f"{model:16} not available here: {type(error).__name__}: {str(error)[:80]}")
            continue
        rate = len(texts) / (time.time() - started)
        same = ""
        if backend == "cpu":
            reference[name] = embedded
        elif name in reference:
            same = f"{mean_cosine(reference[name], embedded):.3f}"
        print(
            f"{model:16} {len(embedded[0]):>5} {rate:>9.1f} {minutes(total / rate):>14} "
            f"{minutes(500_000 / rate):>10} {same}"
        )


def mean_cosine(a: list[list[float]], b: list[list[float]]) -> float:
    """How alike two sets of vectors for the same texts are, on average (1 = identical)."""

    def cosine(x: list[float], y: list[float]) -> float:
        dot = sum(i * j for i, j in zip(x, y, strict=True))
        return dot / (sum(i * i for i in x) ** 0.5 * sum(j * j for j in y) ** 0.5)

    return sum(cosine(x, y) for x, y in zip(a, b, strict=True)) / len(a)


def minutes(seconds: float) -> str:
    return f"{seconds / 60:.0f} min" if seconds < 7200 else f"{seconds / 3600:.1f} hours"
