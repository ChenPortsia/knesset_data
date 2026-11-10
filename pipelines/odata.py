"""Load Knesset OData v4 tables into the `bronze` schema of the DuckDB warehouse.

Run:  python -m pipelines.odata                 # all tables
      python -m pipelines.odata KNS_Person ...  # only some tables

Tables with `LastUpdatedDate` load incrementally: each run fetches only rows
changed since the last run and merges them on `Id`. Lookup tables without it
are fully replaced every run.
"""

import os
import sys
from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Any

import dlt
from dlt.sources.helpers import requests

BASE_URL = "https://knesset.gov.il/OdataV4/ParliamentInfo/"
DB_PATH = os.environ.get("KNESSET_DB", "data/knesset.duckdb")

# Table name -> True if it has `LastUpdatedDate` (incremental), False if not (full replace).
TABLES: dict[str, bool] = {
    # People, factions, positions
    "KNS_Person": True,
    "KNS_PersonToPosition": True,
    "KNS_Position": True,
    "KNS_Faction": True,
    "KNS_KnessetDates": True,
    "KNS_GovMinistry": True,
    # Committees and sessions
    "KNS_Committee": True,
    "KNS_CommitteeSession": True,
    "KNS_CmtSessionItem": True,
    "KNS_PlenumSession": True,
    "KNS_PlmSessionItem": True,
    # Bills, laws, votes
    "KNS_Bill": True,
    "KNS_BillInitiator": True,
    "KNS_IsraelLaw": True,
    "KNS_PlenumVote": True,
    "KNS_PlenumVoteResult": True,
    # Oversight
    "KNS_Query": True,
    "KNS_Agenda": True,
    # Lookups
    "KNS_Status": True,
    "KNS_ItemType": False,
}

Row = dict[str, Any]
GetJson = Callable[[str, dict[str, str]], dict[str, Any]]


def get_json(url: str, params: dict[str, str]) -> dict[str, Any]:
    """GET a URL and return its JSON body (dlt's requests retries on failure)."""
    response = requests.get(url, params=params, timeout=120)
    response.raise_for_status()
    return response.json()


def build_filter(last_id: int, since: datetime | None) -> str:
    """OData filter for the next page: rows after `last_id`, changed since `since`."""
    condition = f"Id gt {last_id}"
    if since is not None:
        condition += f" and LastUpdatedDate ge {since.isoformat()}"
    return condition


def fetch_pages(
    table: str, since: datetime | None = None, get: GetJson = get_json
) -> Iterator[list[Row]]:
    """Yield a table page by page, ordered by `Id`.

    We page with `Id gt <last id>` instead of following `@odata.nextLink`:
    the API's next links use `$skip`, which gets slower the deeper you go
    (15s+ per page on the 2M-row vote table), while keyset paging stays ~1s.
    """
    last_id = 0
    while True:
        params = {"$filter": build_filter(last_id, since), "$orderby": "Id"}
        page = get(BASE_URL + table, params)["value"]
        if not page:
            return
        yield page
        last_id = page[-1]["Id"]


def parse_row(row: Row) -> Row:
    """Turn `LastUpdatedDate` into a datetime so dlt can compare it across time zones."""
    if row.get("LastUpdatedDate"):
        row["LastUpdatedDate"] = datetime.fromisoformat(row["LastUpdatedDate"])
    return row


def table_rows(
    table: str, updated: dlt.sources.incremental[datetime] | None = None
) -> Iterator[list[Row]]:
    """Rows of one table; with `updated`, only rows changed since the last run."""
    since = updated.last_value if updated is not None else None
    for page in fetch_pages(table, since):
        yield [parse_row(row) for row in page]


@dlt.source(name="knesset_odata")
def knesset_odata(tables: list[str] | None = None) -> Iterator[Any]:
    """One dlt resource per OData table."""
    for table in tables or list(TABLES):
        incremental = TABLES[table]
        resource = dlt.resource(
            table_rows,
            name=table,
            primary_key="Id",
            write_disposition="merge" if incremental else "replace",
            parallelized=True,
        )
        updated = dlt.sources.incremental("LastUpdatedDate") if incremental else None
        yield resource(table, updated)


def main(tables: list[str]) -> None:
    pipeline = dlt.pipeline(
        pipeline_name="knesset_odata",
        destination=dlt.destinations.duckdb(DB_PATH),
        dataset_name="bronze",
        progress="log",
    )
    load_info = pipeline.run(knesset_odata(tables or None))
    print(load_info)


if __name__ == "__main__":
    main(sys.argv[1:])
