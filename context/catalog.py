"""Context items generated from dbt: the schema catalog and the metrics. Never edited by hand.

Reads transformation/target/manifest.json and semantic_manifest.json (written by dbt parse).
"""

import json
from pathlib import Path
from typing import Any

TARGET = Path(__file__).resolve().parents[1] / "transformation" / "target"
GOLD_PATH = "3_mart/"


def load_manifest() -> dict[str, Any]:
    path = TARGET / "manifest.json"
    if not path.exists():
        raise SystemExit(
            "No dbt manifest: run `dbt parse` in transformation/ first (make context does)"
        )
    return json.loads(path.read_text())


def split_description(text: str) -> tuple[str, str]:
    """Our descriptions are 'English | Hebrew'."""
    english, _, hebrew = (text or "").partition(" | ")
    return english.strip(), hebrew.strip()


def gold_models(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Gold models by name, with their columns."""
    return {
        node["name"]: node
        for node in manifest["nodes"].values()
        if node["resource_type"] == "model"
        and node["original_file_path"].startswith(f"models/{GOLD_PATH}")
    }


def joins(manifest: dict[str, Any]) -> dict[str, list[str]]:
    """model -> 'model.column -> other.column', from relationship tests."""
    found: dict[str, list[str]] = {}
    for node in manifest["nodes"].values():
        meta = node.get("test_metadata") or {}
        if meta.get("name") != "relationships":
            continue
        model = node["attached_node"].split(".")[-1]
        target = meta["kwargs"]["to"].split("'")[1]  # "ref('dim_person')"
        found.setdefault(model, []).append(
            f"{model}.{node['column_name']} -> {target}.{meta['kwargs']['field']}"
        )
    return found


def catalog_items(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """One item per gold table and one per column."""
    items = []
    model_joins = joins(manifest)
    for name, node in sorted(gold_models(manifest).items()):
        english, hebrew = split_description(node.get("description", ""))
        columns = node["columns"]
        items.append(
            {
                "id": f"table.{name}",
                "kind": "table",
                "title": name,
                "text": english,
                "text_he": hebrew,
                "payload": {
                    "columns": list(columns),
                    "joins": sorted(model_joins.get(name, [])),
                    "contract": node.get("config", {}).get("contract", {}).get("enforced", False),
                },
            }
        )
        for column, spec in columns.items():
            c_english, c_hebrew = split_description(spec.get("description", ""))
            items.append(
                {
                    "id": f"column.{name}.{column}",
                    "kind": "column",
                    "title": f"{name}.{column}",
                    "text": c_english,
                    "text_he": c_hebrew,
                    "payload": {"model": name, "data_type": spec.get("data_type")},
                }
            )
    return items


def metric_items() -> list[dict[str, Any]]:
    """One item per MetricFlow metric. Compute one with: mf query --metrics <name> --group-by ..."""
    path = TARGET / "semantic_manifest.json"
    if not path.exists():
        return []
    items = []
    for metric in json.loads(path.read_text())["metrics"]:
        english, hebrew = split_description(metric.get("description") or "")
        items.append(
            {
                "id": f"metric.{metric['name']}",
                "kind": "metric",
                "title": metric.get("label") or metric["name"],
                "text": english,
                "text_he": hebrew,
                "payload": {"name": metric["name"], "type": metric["type"]},
            }
        )
    return items
