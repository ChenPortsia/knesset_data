"""Survey the OData tables we don't load: how big, which columns, what a row looks like.

    python -m ingestion.survey          (make odata-survey)

Loads nothing. Writes docs/odata_survey.md: for each table of the API that ingestion skips,
its row count, its columns and its newest rows; and for the document tables, which kinds of
document and file they link to (from their 300 newest rows). Run it before deciding to add
a source.
"""

import json
from collections import Counter
from pathlib import Path
from typing import Any

from ingestion.odata import TABLES, Api, load_settings

REPORT = Path(__file__).resolve().parents[1] / "docs" / "odata_survey.md"
NEWEST = {"$orderby": "Id desc", "$top": "100"}


def newest(api: Api, table: str, pages: int = 1) -> list[dict[str, Any]]:
    """The newest rows of a table, 100 per page, paging by key."""
    rows: list[dict[str, Any]] = []
    for _ in range(pages):
        params = NEWEST | ({"$filter": f"Id lt {rows[-1]['Id']}"} if rows else {})
        page = api.json(table, params)["value"]
        rows += page
        if len(page) < 100:
            break
    return rows


def survey(api: Api, table: str) -> str:
    """One table's section of the report."""
    try:
        count = api.json(table, {"$count": "true", "$top": "0"}).get("@odata.count")
        rows = newest(api, table, pages=3 if "Document" in table else 1)
    except Exception as error:
        return f"## {table}\n\nCould not be read: {type(error).__name__}: {str(error)[:200]}\n"
    lines = [f"## {table}", "", f"Rows: {count:,}" if count is not None else "Rows: unknown"]
    if not rows:
        return "\n".join([*lines, "", "No rows.", ""])
    lines += ["", "Columns: " + ", ".join(f"`{c}`" for c in rows[0] if not c.startswith("@"))]
    for column in ("GroupTypeDesc", "ApplicationDesc"):  # the kind of document and of file
        if column in rows[0]:
            kinds = Counter(str(row[column]) for row in rows).most_common(12)
            lines += ["", f"`{column}` in the {len(rows)} newest rows: "
                      + ", ".join(f"{kind} ({n})" for kind, n in kinds)]  # fmt: skip
    lines += ["", "Newest rows:", "", "```json"]
    lines += [json.dumps(row, ensure_ascii=False, default=str) for row in rows[:2]]
    return "\n".join([*lines, "```", ""])


def main() -> None:
    api = Api(load_settings())
    tables = [e["name"] for e in api.json("", {})["value"]]
    skipped = [t for t in tables if t not in TABLES]
    print(f"{len(tables)} tables in the API; {len(skipped)} not loaded")
    sections = []
    for table in skipped:
        print(f"  {table}", flush=True)
        sections.append(survey(api, table))
    header = (
        "# OData tables we don't load\n\n"
        f"Written by `make odata-survey`. {len(skipped)} of the API's {len(tables)} tables.\n"
    )
    REPORT.write_text(header + "\n" + "\n".join(sections), encoding="utf-8")
    print(f"wrote {REPORT}")


if __name__ == "__main__":
    main()
