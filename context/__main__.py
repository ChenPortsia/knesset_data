"""Check, approve and load the context layer.

Run from the repo root:
    python -m context check            # format, unique ids, references to gold (no data needed; CI)
    python -m context build            # check + checks against the data + load into the warehouse
    python -m context approve vq.<id>  # store a verified query's current result as expected
    python -m context schemas          # write JSON Schemas for editors (context/schemas/)

Hand-written items live in context/<kind>/*.yml; generated items come from dbt (catalog.py).
Everything is loaded into the `context` schema of data/warehouse/warehouse.duckdb.
"""

import argparse
import csv
import io
import json
import sys
from pathlib import Path
from typing import Any

import duckdb
import yaml
from pydantic import ValidationError

from context.catalog import TARGET, catalog_items, gold_models, load_manifest, metric_items
from context.items import KINDS, Alias, GlossaryTerm, Item, Rule, VerifiedQuery

ROOT = Path(__file__).resolve().parents[1]
CONTEXT = ROOT / "context"
ANALYSES = ROOT / "transformation" / "analyses"
COMPILED_ANALYSES = TARGET / "compiled" / "knesset" / "analyses"
WAREHOUSE = ROOT / "data" / "warehouse" / "warehouse.duckdb"


def relative(path: Path) -> str:
    """A path as shown in messages: relative to the repo when inside it."""
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def load_items() -> tuple[list[tuple[Path, Item]], list[str]]:
    """Every hand-written item with its file, and the errors found while reading them."""
    items, errors = [], []
    for folder, (model, _) in KINDS.items():
        for path in sorted((CONTEXT / folder).glob("*.yml")):
            entries = yaml.safe_load(path.read_text(encoding="utf-8")) or []
            for i, entry in enumerate(entries):
                try:
                    items.append((path, model.model_validate(entry)))
                except ValidationError as error:
                    where = f"{relative(path)} item {i + 1} ({entry.get('id', 'no id')})"
                    errors += [f"{where}: {e['loc']}: {e['msg']}" for e in error.errors()]
    return items, errors


def static_errors(items: list[tuple[Path, Item]], manifest: dict[str, Any]) -> list[str]:
    """Problems found without data: duplicates, and references to things that don't exist."""
    errors = []
    models = gold_models(manifest)
    columns = {f"{m}.{c}" for m, node in models.items() for c in node["columns"]}
    ids = [item.id for _, item in items]
    generated = {i["id"] for i in catalog_items(manifest) + metric_items()}
    errors += [f"duplicate id: {i}" for i in sorted({i for i in ids if ids.count(i) > 1})]

    alias_names: dict[str, str] = {}
    for path, item in items:
        where = f"{relative(path)} {item.id}"
        refs: list[str] = []
        if isinstance(item, GlossaryTerm):
            refs = [m.column for m in item.maps_to]
            errors += [
                f"{where}: see_also {s} is not an item"
                for s in item.see_also
                if s not in ids and s not in generated
            ]
        elif isinstance(item, Alias):
            refs = [item.resolves_to.column]
            for name in item.names:
                if (other := alias_names.setdefault(name.strip(), item.id)) != item.id:
                    errors.append(f"{where}: name '{name}' is also in {other}")
        elif isinstance(item, Rule):
            refs = item.applies_to
        elif isinstance(item, VerifiedQuery) and not (ANALYSES / item.sql_file).exists():
            errors.append(
                f"{where}: sql_file transformation/analyses/{item.sql_file} does not exist"
            )
        for ref in refs:
            if ref not in columns and ref not in models:
                errors.append(f"{where}: {ref} is not a gold model or column")
    return errors


def query_result(con: duckdb.DuckDBPyConnection, vq: VerifiedQuery) -> str:
    """Run a verified query's compiled SQL and return its result as CSV text."""
    path = COMPILED_ANALYSES / vq.sql_file
    if not path.exists():
        raise FileNotFoundError(f"{path} not compiled: run `dbt compile` in transformation/")
    cursor = con.execute(path.read_text())
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow([c[0] for c in cursor.description])
    writer.writerows(cursor.fetchall())
    return out.getvalue()


def expected_path(vq: VerifiedQuery) -> Path:
    return CONTEXT / "expected" / f"{vq.id}.csv"


def data_errors(items: list[tuple[Path, Item]], con: duckdb.DuckDBPyConnection) -> list[str]:
    """Problems found against the data: values that don't exist, queries that don't match."""
    errors = []

    def value_exists(column_ref: str, value: Any) -> bool:
        model, column = column_ref.split(".")
        return (
            con.execute(
                f"SELECT COUNT(*) FROM gold.{model} WHERE {column} = ?", [value]
            ).fetchone()[0]
            > 0
        )

    for path, item in items:
        where = f"{relative(path)} {item.id}"
        if isinstance(item, GlossaryTerm):
            errors += [
                f"{where}: no row has {m.column} = {m.value!r}"
                for m in item.maps_to
                if m.value is not None and not value_exists(m.column, m.value)
            ]
        elif isinstance(item, Alias):
            errors += [
                f"{where}: no row has {item.resolves_to.column} = {v!r}"
                for v in item.resolves_to.values
                if not value_exists(item.resolves_to.column, v)
            ]
        elif isinstance(item, VerifiedQuery):
            if not expected_path(item).exists():
                errors.append(
                    f"{where}: no expected result; run `python -m context approve {item.id}`"
                )
                continue
            try:
                actual = query_result(con, item)
            except Exception as error:
                errors.append(f"{where}: query failed: {error}")
                continue
            expected = expected_path(item).read_text(encoding="utf-8")
            if item.stable and actual != expected:
                errors.append(f"{where}: result differs from {relative(expected_path(item))}")
            elif actual.splitlines()[0] != expected.splitlines()[0]:
                errors.append(
                    f"{where}: result columns differ from {relative(expected_path(item))}"
                )
            elif len(actual.splitlines()) < 2:
                errors.append(f"{where}: query returned no rows")
    return errors


def to_rows(items: list[tuple[Path, Item]], manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Hand-written and generated items as rows of context.items."""
    rows = []
    for path, item in items:
        kind = next(kind for model, kind in KINDS.values() if isinstance(item, model))
        data = item.model_dump(mode="json")
        if isinstance(item, GlossaryTerm):
            title, text, text_he = (
                item.term_en,
                item.definition,
                " / ".join([item.term_he, *item.synonyms]),
            )
        elif isinstance(item, Alias):
            title, text, text_he = item.id, item.note or "", " / ".join(item.names)
        elif isinstance(item, Rule):
            title, text, text_he = item.title, item.rule, ""
        else:
            title, text, text_he = item.question_en, item.question_en, item.question_he
            data["sql"] = (COMPILED_ANALYSES / item.sql_file).read_text()
        rows.append({
            "id": item.id, "kind": kind, "title": title, "text": text, "text_he": text_he,
            "source": str(relative(path)), "payload": data,
        })  # fmt: skip
    for generated in catalog_items(manifest) + metric_items():
        rows.append({**generated, "source": "dbt"})
    return rows


def load(con: duckdb.DuckDBPyConnection, rows: list[dict[str, Any]]) -> None:
    """Replace the context schema with the current items."""
    con.execute("CREATE SCHEMA IF NOT EXISTS context")
    con.execute(
        """
        CREATE OR REPLACE TABLE context.items (
            id VARCHAR PRIMARY KEY,
            kind VARCHAR NOT NULL,
            title VARCHAR,
            text VARCHAR,
            text_he VARCHAR,
            source VARCHAR,
            payload JSON
        )
        """
    )
    con.executemany(
        "INSERT INTO context.items VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (
                r["id"],
                r["kind"],
                r["title"],
                r["text"],
                r["text_he"],
                r["source"],
                json.dumps(r["payload"], ensure_ascii=False),
            )
            for r in rows
        ],
    )


def report(title: str, errors: list[str]) -> bool:
    if errors:
        print(f"{title}: {len(errors)} problem(s)")
        for error in errors:
            print(f"  - {error}")
    return not errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Check, approve and load the context layer")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="format and references, no data needed")
    sub.add_parser("build", help="check, check against the data, load into the warehouse")
    approve = sub.add_parser("approve", help="store verified queries' current results as expected")
    approve.add_argument("ids", nargs="+", help="verified query ids, or 'all'")
    sub.add_parser("schemas", help="write JSON Schemas for editors")
    args = parser.parse_args()

    if args.command == "schemas":
        (CONTEXT / "schemas").mkdir(exist_ok=True)
        for folder, (model, _) in KINDS.items():
            schema = {"type": "array", "items": model.model_json_schema()}
            (CONTEXT / "schemas" / f"{folder}.json").write_text(
                json.dumps(schema, indent=2, ensure_ascii=False) + "\n"
            )
        print(f"wrote {len(KINDS)} schemas to context/schemas/")
        return 0

    items, errors = load_items()
    manifest = load_manifest()
    if not report("format", errors) or not report("references", static_errors(items, manifest)):
        return 1
    counts = {kind: sum(isinstance(i, model) for _, i in items) for model, kind in KINDS.values()}
    print(f"check ok: {counts}")
    if args.command == "check":
        return 0

    with duckdb.connect(str(WAREHOUSE), read_only=args.command == "approve") as con:
        if args.command == "approve":
            queries = [i for _, i in items if isinstance(i, VerifiedQuery)]
            chosen = queries if args.ids == ["all"] else [q for q in queries if q.id in args.ids]
            for vq in chosen:
                expected_path(vq).parent.mkdir(exist_ok=True)
                expected_path(vq).write_text(query_result(con, vq), encoding="utf-8")
                print(f"approved {vq.id} -> {relative(expected_path(vq))}")
            return 0
        if not report("data", data_errors(items, con)):
            return 1
        rows = to_rows(items, manifest)
        load(con, rows)
        kinds = {k: sum(r["kind"] == k for r in rows) for k in sorted({r["kind"] for r in rows})}
        print(f"loaded {len(rows)} items into context.items: {kinds}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
