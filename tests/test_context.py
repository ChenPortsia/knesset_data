"""The context checks must catch broken items, not just pass good ones."""

from pathlib import Path

import duckdb
import pytest
from pydantic import ValidationError

import context.__main__ as build
from context.items import Alias, GlossaryTerm, Rule, VerifiedQuery

FILE = Path(build.CONTEXT / "glossary" / "test.yml")
MANIFEST = {
    "nodes": {
        "model.knesset.dim_bill": {
            "resource_type": "model",
            "name": "dim_bill",
            "original_file_path": "models/3_mart/legislation/dim_bill.sql",
            "columns": {"bill_id": {}, "is_passed": {}, "origin": {}},
        },
        "model.knesset.stg_odata__bill": {
            "resource_type": "model",
            "name": "stg_odata__bill",
            "original_file_path": "models/1_staging/odata/stg_odata__bill.sql",
            "columns": {"bill_id": {}},
        },
    }
}


def term(**changes) -> GlossaryTerm:
    fields = {
        "id": "glossary.law",
        "term_he": "חוק",
        "term_en": "law",
        "definition": "A passed bill.",
    }
    return GlossaryTerm(**{**fields, **changes})


def alias(id_: str, names: list[str], column: str = "dim_bill.bill_id") -> Alias:
    return Alias(id=id_, names=names, resolves_to={"column": column, "values": [1]})


def errors(*items) -> list[str]:
    return build.static_errors([(FILE, item) for item in items], MANIFEST)


def test_a_misspelled_field_is_an_error_not_ignored():
    with pytest.raises(ValidationError):
        term(defintion="typo")
    with pytest.raises(ValidationError):
        term(id="law")  # ids need their kind as a prefix


def test_good_items_pass():
    assert errors(term(maps_to=[{"column": "dim_bill.is_passed", "value": True}])) == []


def test_references_must_be_gold_columns():
    assert errors(term(maps_to=[{"column": "dim_bill.no_such_column"}]))
    assert errors(term(maps_to=[{"column": "stg_odata__bill.bill_id"}]))  # silver, not gold
    assert errors(Rule(id="rule.x", title="x", rule="x", applies_to=["fct_missing"]))


def test_ids_and_alias_names_must_be_unique():
    assert any("duplicate id" in e for e in errors(term(), term()))
    same_name = errors(alias("alias.a", ["ועדת חוץ"]), alias("alias.b", [" ועדת חוץ"]))
    assert any("also in alias.a" in e for e in same_name)


def test_see_also_must_point_to_an_item():
    assert errors(term(see_also=["glossary.missing"]))


def test_verified_query_needs_its_sql_file():
    vq = VerifiedQuery(
        id="vq.x", question_en="?", question_he="?", sql_file="missing/q.sql",
        stable=True, verified_by="me", verified_at="2026-11-11",
    )  # fmt: skip
    assert any("does not exist" in e for e in errors(vq))


@pytest.fixture
def warehouse():
    con = duckdb.connect()
    con.execute(
        "CREATE SCHEMA gold; CREATE TABLE gold.dim_bill AS SELECT 1 AS bill_id, 'private' AS origin"
    )
    return con


def test_values_must_exist_in_the_data(warehouse):
    good = term(maps_to=[{"column": "dim_bill.origin", "value": "private"}])
    bad = term(id="glossary.bad", maps_to=[{"column": "dim_bill.origin", "value": "privat"}])
    assert build.data_errors([(FILE, good)], warehouse) == []
    assert build.data_errors([(FILE, bad)], warehouse)
    assert build.data_errors([(FILE, alias("alias.x", ["x"]))], warehouse) == []
    missing = Alias(
        id="alias.y", names=["y"], resolves_to={"column": "dim_bill.bill_id", "values": [2]}
    )
    assert build.data_errors([(FILE, missing)], warehouse)


def test_a_stable_verified_query_must_match_its_expected_result(warehouse, tmp_path, monkeypatch):
    monkeypatch.setattr(build, "COMPILED_ANALYSES", tmp_path)
    monkeypatch.setattr(build, "CONTEXT", tmp_path)
    (tmp_path / "q.sql").write_text(
        "SELECT origin, COUNT(*) AS bills FROM gold.dim_bill GROUP BY 1"
    )
    (tmp_path / "expected").mkdir()
    vq = VerifiedQuery(
        id="vq.q", question_en="?", question_he="?", sql_file="q.sql",
        stable=True, verified_by="me", verified_at="2026-11-11",
    )  # fmt: skip
    (tmp_path / "expected" / "vq.q.csv").write_text("origin,bills\nprivate,1\n")
    assert build.data_errors([(tmp_path / "x.yml", vq)], warehouse) == []
    (tmp_path / "expected" / "vq.q.csv").write_text("origin,bills\nprivate,2\n")
    assert any("differs" in e for e in build.data_errors([(tmp_path / "x.yml", vq)], warehouse))
