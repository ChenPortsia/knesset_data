"""The search index over the context items: keywords and meaning.

Built by `python -m context build` into two tables of the `context` schema:
    context.search  one row per item: the text that is searched, and its embedding
    context.build   which embedding model was used, and when

The agent's get_context (knesset-agent/tools/context.py) searches both ways and merges the
two rankings. A question must be embedded with the same model, so the model's name is stored.

The model was chosen by test, on knesset-agent's question bank (evals/): see the README.
"""

from collections.abc import Callable

import duckdb

# Turns a text into 1,024 numbers; texts with a similar meaning get similar numbers, in any
# of ~100 languages. 2.2 GB, downloaded once. It expects a prefix saying what a text is.
MODEL = "intfloat/multilingual-e5-large"
ITEM_PREFIX = "passage: "
QUESTION_PREFIX = "query: "
# What separates words for keyword search: anything but Latin letters, digits and Hebrew letters
NOT_A_WORD = "[^a-z0-9א-ת]+"

Embed = Callable[[list[str]], list[list[float]]]


def embed(texts: list[str]) -> list[list[float]]:
    from fastembed import TextEmbedding  # here, not at the top: slow, and only `build` needs it

    vectors = TextEmbedding(MODEL).embed([ITEM_PREFIX + text for text in texts])
    return [vector.tolist() for vector in vectors]


def embedded_before(con: duckdb.DuckDBPyConnection, model: str) -> dict[str, list[float]]:
    """text -> embedding from the last build with the same model, so only new texts are embedded."""
    try:
        return dict(
            con.execute(
                """
                SELECT search_text, embedding FROM context.search
                WHERE (SELECT embedding_model FROM context.build) = ?
                """,
                [model],
            ).fetchall()
        )
    except duckdb.CatalogException:  # first build
        return {}


def build_index(con: duckdb.DuckDBPyConnection, embed: Embed = embed, model: str = MODEL) -> None:
    """Rebuild context.search and context.build from context.items."""
    rows = con.execute(
        "SELECT id, CONCAT_WS(' ', title, text, text_he) FROM context.items ORDER BY id"
    ).fetchall()
    known = embedded_before(con, model)
    new = sorted({text for _, text in rows} - set(known))
    known.update(zip(new, embed(new) if new else [], strict=True))
    vectors = [known[text] for _, text in rows]
    print(f"embedded {len(new)} new or changed items of {len(rows)}")
    con.execute(
        f"""
        CREATE OR REPLACE TABLE context.search (
            id VARCHAR PRIMARY KEY,
            search_text VARCHAR,
            embedding FLOAT[{len(vectors[0])}]
        )
        """
    )
    con.executemany(
        "INSERT INTO context.search VALUES (?, ?, ?)",
        [(id_, text, vector) for (id_, text), vector in zip(rows, vectors, strict=True)],
    )
    # Keyword index (BM25). No stemmer or stopword list: they are English-only.
    con.execute("INSTALL fts; LOAD fts")
    con.execute(
        f"""
        PRAGMA create_fts_index(
            'context.search', 'id', 'search_text',
            stemmer = 'none', stopwords = 'none', ignore = '{NOT_A_WORD}', overwrite = 1
        )
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE context.build AS
        SELECT
            ? AS embedding_model,
            ? AS question_prefix,
            CURRENT_TIMESTAMP AS built_at,
            ? AS items
        """,
        [model, QUESTION_PREFIX, len(rows)],
    )
