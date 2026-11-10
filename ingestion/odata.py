"""Knesset OData v4 API client and the dlt resource for one table.

Scope: only the 20th Knesset onward (2015-03-31 to today), which covers the
committee protocols (Nov 2018+). Change `FROM_KNESSET` / `FROM_DATE` to widen it.
"""

import queue
import threading
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import dlt
from dlt.extract.resource import DltResource
from dlt.sources.helpers.requests import Client

BASE_URL = "https://knesset.gov.il/OdataV4/ParliamentInfo/"
FROM_KNESSET = 20
FROM_DATE = "2015-03-31T00:00:00+03:00"  # the 20th Knesset was sworn in
WORKERS = 8  # parallel requests per table; the API handled 16, 8 stays polite
ROWS_PER_RANGE = 20_000  # split a table into parallel Id ranges of about this size
LAG_SECONDS = 3600  # re-read the last hour each run, for rows committed late


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

# The site's firewall sometimes answers a burst of requests with non-standard 4xx codes
# (seen: 473, 481) for a few seconds. Retry those like rate limits (429) and server errors
# (5xx), with exponential backoff: 1, 2, 4 ... 64s, up to 8 attempts.
RETRY_STATUS = (429, *range(470, 500), *range(500, 600))
http = Client(
    request_timeout=120,
    status_codes=RETRY_STATUS,
    request_max_attempts=8,
    request_backoff_factor=2,
).session

Row = dict[str, Any]
GetJson = Callable[[str, dict[str, str]], dict[str, Any]]


def get_json(url: str, params: dict[str, str]) -> dict[str, Any]:
    """GET a URL and return its JSON body; retries as set on `http` above."""
    response = http.get(url, params=params)
    response.raise_for_status()
    return response.json()


def get_metadata() -> bytes:
    """The API's `$metadata` XML: every table with its typed columns."""
    return http.get(BASE_URL + "$metadata").content


def table_columns(metadata: bytes, table: str) -> dict[str, dict[str, Any]]:
    """dlt column hints for one table, read from the `$metadata` XML."""
    for entity in ET.fromstring(metadata).iter(f"{EDM}EntityType"):
        if entity.get("Name") == table:
            return {
                prop.get("Name"): {"data_type": DLT_TYPES[prop.get("Type")], "nullable": True}
                for prop in entity.iter(f"{EDM}Property")
            }
    raise KeyError(f"{table} not in $metadata")


def build_filter(
    where: str | None = None,
    since: datetime | None = None,
    after: int | None = None,
    upto: int | None = None,
) -> str | None:
    """OData filter: rows in scope, changed since `since`, with `after < Id <= upto`."""
    conditions = []
    if after is not None:
        conditions.append(f"Id gt {after}")
    if upto is not None:
        conditions.append(f"Id le {upto}")
    if where:
        conditions.append(where)
    if since is not None:
        conditions.append(f"LastUpdatedDate ge {since.isoformat()}")
    return " and ".join(conditions) or None


def params_for(filter_: str | None, **extra: str) -> dict[str, str]:
    return {**({"$filter": filter_} if filter_ else {}), **extra}


def api_count(table: str, where: str | None = None, get: GetJson = get_json) -> int:
    """Number of rows the API has for a table in our scope."""
    params = params_for(build_filter(where), **{"$count": "true", "$top": "0"})
    return get(BASE_URL + table, params)["@odata.count"]


def edge_id(
    table: str, where: str | None, since: datetime | None, last: bool, get: GetJson = get_json
) -> int | None:
    """Smallest (or with `last`, largest) Id matching the filter; None if no rows."""
    order = "Id desc" if last else "Id"
    params = params_for(
        build_filter(where, since), **{"$select": "Id", "$orderby": order, "$top": "1"}
    )
    rows = get(BASE_URL + table, params)["value"]
    return rows[0]["Id"] if rows else None


def id_ranges(low: int, high: int, parts: int) -> list[tuple[int, int]]:
    """Split the Ids in (low, high] into `parts` ranges of (after, upto]."""
    step = -(-(high - low) // parts)  # ceiling division
    return [(start, min(start + step, high)) for start in range(low, high, step)]


def check_page(table: str, page: list[Row], after: int) -> None:
    """Every row needs an Id, in increasing order after the previous page. Raises if not."""
    previous = after
    for row in page:
        row_id = row.get("Id")
        if not isinstance(row_id, int) or row_id <= previous:
            raise ValueError(f"{table}: bad or out-of-order Id {row_id!r} after {previous}")
        previous = row_id


def fetch_range(
    table: str,
    where: str | None,
    since: datetime | None,
    after: int,
    upto: int,
    select: str | None = None,
    get: GetJson = get_json,
) -> Iterator[list[Row]]:
    """Pages of rows with `after < Id <= upto`, 100 at a time, ordered by Id.

    We page with `Id gt <last id>` instead of following `@odata.nextLink`:
    the API's next links use `$skip`, which gets slower the deeper you go
    (15s+ per page on the 2M-row vote table), while keyset paging stays ~1s.
    """
    last = after
    while True:
        extra = {"$orderby": "Id", **({"$select": select} if select else {})}
        page = get(BASE_URL + table, params_for(build_filter(where, since, last, upto), **extra))[
            "value"
        ]
        if not page:
            return
        check_page(table, page, last)
        yield page
        last = page[-1]["Id"]


def merge_pages(iterators: list[Iterator[list[Row]]]) -> Iterator[list[Row]]:
    """Run page iterators in parallel threads and yield their pages as they arrive."""
    pages: queue.Queue = queue.Queue(maxsize=2 * len(iterators))
    stop = threading.Event()
    done = object()

    def drain(pages_of_range: Iterator[list[Row]]) -> None:
        try:
            for page in pages_of_range:
                while not stop.is_set():
                    try:
                        pages.put(page, timeout=1)
                        break
                    except queue.Full:
                        continue
            pages.put(done)
        except Exception as error:  # hand the error to the consumer, which re-raises it
            pages.put(error)

    with ThreadPoolExecutor(len(iterators)) as pool:
        for pages_of_range in iterators:
            pool.submit(drain, pages_of_range)
        try:
            finished = 0
            while finished < len(iterators):
                item = pages.get()
                if item is done:
                    finished += 1
                elif isinstance(item, Exception):
                    raise item
                else:
                    yield item
        finally:
            stop.set()  # unblock the threads if we stop early (error or sample limit)
            while not pages.empty():
                pages.get_nowait()


def fetch_table(
    table: str,
    where: str | None = None,
    since: datetime | None = None,
    select: str | None = None,
    workers: int = WORKERS,
    get: GetJson = get_json,
) -> Iterator[list[Row]]:
    """All pages of a table. Large tables are split into Id ranges fetched in parallel."""
    low = edge_id(table, where, since, last=False, get=get)
    if low is None:
        return
    high = edge_id(table, where, since, last=True, get=get)
    parts = max(1, min(workers, (high - low) // ROWS_PER_RANGE))
    ranges = id_ranges(low - 1, high, parts)
    iterators = [fetch_range(table, where, since, a, b, select, get) for a, b in ranges]
    yield from iterators[0] if parts == 1 else merge_pages(iterators)


def parse_row(row: Row) -> Row:
    """Turn `LastUpdatedDate` into a datetime so dlt can compare it across time zones."""
    if row.get("LastUpdatedDate"):
        row["LastUpdatedDate"] = datetime.fromisoformat(row["LastUpdatedDate"])
    return row


def table_rows(
    table: str,
    where: str | None,
    updated: dlt.sources.incremental[datetime] | None = None,
    workers: int = WORKERS,
) -> Iterator[list[Row]]:
    """Rows of one table; with `updated`, only rows changed since the last run (minus the lag)."""
    since = updated.start_value if updated is not None else None
    for page in fetch_table(table, where, since, workers=workers):
        yield [parse_row(row) for row in page]


def table_resource(name: str, metadata: bytes, workers: int = WORKERS) -> DltResource:
    """The dlt resource for one table.

    Incremental tables use SCD2: bronze keeps every version of a row, with
    `_dlt_valid_from` / `_dlt_valid_to`; the current version has `_dlt_valid_to` null.
    Rows that did not change produce the same row hash, so reruns add nothing.
    """
    table = TABLES[name]
    if table.incremental:
        disposition: Any = {"disposition": "merge", "strategy": "scd2"}
        updated = dlt.sources.incremental[datetime]("LastUpdatedDate", lag=LAG_SECONDS)
    else:
        disposition, updated = "replace", None
    resource = dlt.resource(
        table_rows,
        name=name,
        columns=table_columns(metadata, name),
        write_disposition=disposition,
        primary_key=None if table.incremental else "Id",
        merge_key="Id" if table.incremental else None,  # absent rows are not retired
        # A changed column type fails the load; new columns are added (and logged).
        schema_contract={"tables": "evolve", "columns": "evolve", "data_type": "freeze"},
    )
    return resource(name, table.where, updated, workers)
