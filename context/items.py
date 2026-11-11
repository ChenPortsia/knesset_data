"""The kinds of hand-written context items, and the rules each one must follow.

Each class is one kind of item, written in YAML files in its own folder (glossary/,
aliases/, rules/, verified_queries/). The field descriptions below are also exported as
JSON Schemas (context/schemas/), so editors can autocomplete and check the YAML.
"""

from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

# A column in a gold model, written as model.column (e.g. dim_bill.is_passed)
ColumnRef = Annotated[
    str, Field(pattern=r"^[a-z_0-9]+\.[a-z_0-9]+$", examples=["dim_bill.is_passed"])
]
# A gold model or one of its columns
ModelOrColumnRef = Annotated[
    str, Field(pattern=r"^[a-z_0-9]+(\.[a-z_0-9]+)?$", examples=["fct_vote_result"])
]


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid")  # a misspelled field is an error, not ignored


class Mapping(Item):
    column: ColumnRef = Field(description="Where the term shows up in gold: model.column")
    value: str | int | bool | None = Field(
        default=None, description="The value that means the term, if it is one value of the column"
    )


class GlossaryTerm(Item):
    """A parliamentary term and where it lives in the data."""

    id: str = Field(pattern=r"^glossary\.[a-z0-9_]+$", description="glossary.<snake_case_name>")
    term_he: str = Field(description="The term in Hebrew, as people write it")
    term_en: str = Field(description="The term in English")
    synonyms: list[str] = Field(default=[], description="Other ways to say it, in either language")
    definition: str = Field(description="What it means, in plain English, in a sentence or two")
    maps_to: list[Mapping] = Field(default=[], description="The columns (and values) it maps to")
    see_also: list[str] = Field(default=[], description="Ids of related context items")


class AliasTarget(Item):
    column: ColumnRef = Field(description="The key column the names resolve to, model.column")
    values: list[int | str] = Field(
        min_length=1,
        description=(
            "The key values: one entity, possibly several rows "
            "(e.g. a party's faction in each Knesset)"
        ),
    )


class Alias(Item):
    """Names people use for one entity: a person, committee, party or ministry."""

    id: str = Field(pattern=r"^alias\.[a-z0-9_.]+$", description="alias.<kind>.<name>")
    names: list[str] = Field(
        min_length=1,
        description="Every name for the entity; each may appear in only one alias item",
    )
    resolves_to: AliasTarget
    note: str | None = Field(
        default=None, description="Anything a reader should know, e.g. why some values are left out"
    )


class Rule(Item):
    """How to interpret a question or use the data correctly."""

    id: str = Field(pattern=r"^rule\.[a-z0-9_]+$", description="rule.<snake_case_name>")
    title: str = Field(description="The rule in a few words")
    rule: str = Field(description="The rule itself: what to do, and why")
    applies_to: list[ModelOrColumnRef] = Field(
        default=[], description="Gold models or model.columns the rule is about"
    )


class VerifiedQuery(Item):
    """A question with SQL that is known to answer it correctly."""

    id: str = Field(pattern=r"^vq\.[a-z0-9_]+$", description="vq.<snake_case_name>")
    question_en: str = Field(description="The question in English")
    question_he: str = Field(description="The question in Hebrew, as a user would ask it")
    sql_file: str = Field(
        description="The dbt analysis with the SQL, relative to transformation/analyses/"
    )
    stable: bool = Field(
        description=(
            "True if the answer should not change as new data arrives (e.g. a past Knesset); "
            "its result is then compared exactly"
        )
    )
    verified_by: str = Field(description="Who checked that the SQL answers the question")
    verified_at: date = Field(description="When it was checked")
    onboarding: bool = Field(
        default=False, description="True to suggest this question to new users"
    )


# folder -> (item class, the item's kind in context.items)
KINDS: dict[str, tuple[type[Item], str]] = {
    "glossary": (GlossaryTerm, "glossary"),
    "aliases": (Alias, "alias"),
    "rules": (Rule, "rule"),
    "verified_queries": (VerifiedQuery, "verified_query"),
}
