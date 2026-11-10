"""Load Knesset OData v4 tables into the `bronze` schema of the DuckDB warehouse.

Run:  python -m ingestion.odata                  # full load into data/knesset.duckdb
      python -m ingestion.odata --sample         # 200 rows per table into data/sample.duckdb
      python -m ingestion.odata KNS_Person ...   # only some tables

Scope: only the 20th Knesset onward (2015-03-31 to today), which covers the
committee protocols (Nov 2018+). Change `FROM_KNESSET` / `FROM_DATE` to widen it.

Tables with `LastUpdatedDate` load incrementally: each run fetches only rows
changed since the last run and merges them on `Id`. Lookup tables without it
are fully replaced every run.
"""

import argparse
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import dlt
from dlt.sources.helpers import requests

BASE_URL = "https://knesset.gov.il/OdataV4/ParliamentInfo/"
FROM_KNESSET = 20
FROM_DATE = "2015-03-31T00:00:00+03:00"  # the 20th Knesset was sworn in
SAMPLE_PAGES = 2  # 100 rows per page


@dataclass(frozen=True)
class Table:
    where: str | None = None  # extra OData filter that limits the scope
    incremental: bool = True  # False for tables without LastUpdatedDate


BY_KNESSET = f"KnessetNum ge {FROM_KNESSET}"

TABLES: dict[str, Table] = {
    # People, factions, positions
    "KNS_Person": Table(),
    "KNS_PersonToPosition": Table(BY_KNESSET),
    "KNS_Position": Table(),
    "KNS_Faction": Table(BY_KNESSET),
    "KNS_KnessetDates": Table(),
    "KNS_GovMinistry": Table(),
    # Committees and sessions
    "KNS_Committee": Table(BY_KNESSET),
    "KNS_CommitteeSession": Table(BY_KNESSET),
    "KNS_CmtSessionItem": Table(),  # no Knesset/date column; filtered in dbt
    "KNS_PlenumSession": Table(BY_KNESSET),
    "KNS_PlmSessionItem": Table(),  # no Knesset/date column; filtered in dbt
    # Bills, laws, votes
    "KNS_Bill": Table(BY_KNESSET),
    "KNS_BillInitiator": Table(),  # no Knesset/date column; filtered in dbt
    "KNS_IsraelLaw": Table(),  # laws in force may come from any Knesset
    "KNS_PlenumVote": Table(f"VoteDateTime ge {FROM_DATE}"),
    "KNS_PlenumVoteResult": Table(f"VoteDate ge {FROM_DATE}"),
    # Oversight
    "KNS_Query": Table(BY_KNESSET),
    "KNS_Agenda": Table(BY_KNESSET),
    # Lookups
    "KNS_Status": Table(),
    "KNS_ItemType": Table(incremental=False),
}

# OData type -> dlt type. Declaring every column keeps the warehouse schema stable:
# without it dlt skips columns that happen to be all-null in a load.
DLT_TYPES = {
    "Edm.Int16": "bigint",
    "Edm.Int32": "bigint",
    "Edm.Int64": "bigint",
    "Edm.String": "text",
    "Edm.Boolean": "bool",
    "Edm.DateTimeOffset": "timestamp",
}
EDM = "{http://docs.oasis-open.org/odata/ns/edm}"

Row = dict[str, Any]
GetJson = Callable[[str, dict[str, str]], dict[str, Any]]


def get_json(url: str, params: dict[str, str]) -> dict[str, Any]:
    """GET a URL and return its JSON body (dlt's requests retries on failure)."""
    response = requests.get(url, params=params, timeout=120)
    response.raise_for_status()
    return response.json()


def table_columns(metadata: bytes, table: str) -> dict[str, dict[str, Any]]:
    """dlt column hints for one table, read from the API's `$metadata` XML."""
    for entity in ET.fromstring(metadata).iter(f"{EDM}EntityType"):
        if entity.get("Name") == table:
            return {
                prop.get("Name"): {"data_type": DLT_TYPES[prop.get("Type")], "nullable": True}
                for prop in entity.iter(f"{EDM}Property")
            }
    raise KeyError(f"{table} not in $metadata")


def build_filter(last_id: int, where: str | None = None, since: datetime | None = None) -> str:
    """OData filter for the next page: rows after `last_id`, in scope, changed since `since`."""
    conditions = [f"Id gt {last_id}"]
    if where:
        conditions.append(where)
    if since is not None:
        conditions.append(f"LastUpdatedDate ge {since.isoformat()}")
    return " and ".join(conditions)


def fetch_pages(
    table: str, where: str | None = None, since: datetime | None = None, get: GetJson = get_json
) -> Iterator[list[Row]]:
    """Yield a table page by page, ordered by `Id`.

    We page with `Id gt <last id>` instead of following `@odata.nextLink`:
    the API's next links use `$skip`, which gets slower the deeper you go
    (15s+ per page on the 2M-row vote table), while keyset paging stays ~1s.
    """
    last_id = 0
    while True:
        params = {"$filter": build_filter(last_id, where, since), "$orderby": "Id"}
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
    table: str, where: str | None, updated: dlt.sources.incremental[datetime] | None = None
) -> Iterator[list[Row]]:
    """Rows of one table; with `updated`, only rows changed since the last run."""
    since = updated.last_value if updated is not None else None
    for page in fetch_pages(table, where, since):
        yield [parse_row(row) for row in page]


@dlt.source(name="knesset_odata")
def knesset_odata(tables: list[str] | None = None, max_pages: int | None = None) -> Iterator[Any]:
    """One dlt resource per OData table; `max_pages` caps each table for test loads."""
    metadata = requests.get(BASE_URL + "$metadata", timeout=120).content
    for name in tables or list(TABLES):
        table = TABLES[name]
        resource = dlt.resource(
            table_rows,
            name=name,
            primary_key="Id",
            columns=table_columns(metadata, name),
            write_disposition="merge" if table.incremental else "replace",
            parallelized=True,
        )
        updated = dlt.sources.incremental("LastUpdatedDate") if table.incremental else None
        resource = resource(name, table.where, updated)
        yield resource.add_limit(max_pages) if max_pages else resource


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tables", nargs="*", help="table names, default: all")
    parser.add_argument("--sample", action="store_true", help="test load of a few rows per table")
    args = parser.parse_args()
    if unknown := set(args.tables) - set(TABLES):
        parser.error(f"unknown tables: {sorted(unknown)}")

    name = "knesset_sample" if args.sample else "knesset"
    pipeline = dlt.pipeline(
        pipeline_name=name,
        pipelines_dir="data/.dlt",  # pipeline state lives next to the data; delete data/ to reset
        destination=dlt.destinations.duckdb(f"data/{name}.duckdb"),
        dataset_name="bronze",
        progress="log",
    )
    source = knesset_odata(args.tables or None, SAMPLE_PAGES if args.sample else None)
    # A sample starts from scratch every time, so it never blocks a later full load.
    load_info = pipeline.run(source, refresh="drop_sources" if args.sample else None)
    print(load_info)


if __name__ == "__main__":
    main()
