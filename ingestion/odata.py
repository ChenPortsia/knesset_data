"""Knesset OData v4 API client and the dlt source with one resource per table.

Settings come from ingestion/.dlt/config.toml, section [sources.knesset_odata].
"""

import json
import logging
import queue
import threading
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, fields
from datetime import datetime
from typing import Any

import dlt
from dlt.extract.resource import DltResource
from dlt.sources.helpers.requests import Client

log = logging.getLogger("ingestion")


@dataclass(frozen=True)
class Settings:
    base_url: str
    from_knesset: int
    from_date: str
    workers: int
    rows_per_range: int
    lag_seconds: int
    sample_pages: int
    request_timeout: int
    request_max_attempts: int
    request_backoff_factor: float


def load_settings() -> Settings:
    """Read [sources.knesset_odata] from ingestion/.dlt/config.toml (or environment variables)."""
    return Settings(
        **{f.name: dlt.config[f"sources.knesset_odata.{f.name}"] for f in fields(Settings)}
    )


@dataclass(frozen=True)
class Table:
    where: str | None = None  # scope filter; {from_knesset} / {from_date} come from Settings
    incremental: bool = True  # False for tables without LastUpdatedDate


BY_KNESSET = "KnessetNum ge {from_knesset}"

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
    "KNS_PlenumVote": Table("VoteDateTime ge {from_date}"),
    "KNS_PlenumVoteResult": Table("VoteDate ge {from_date}"),
    # Oversight
    "KNS_Query": Table(BY_KNESSET),
    "KNS_Agenda": Table(BY_KNESSET),
    # Lookups
    "KNS_Status": Table(),
    "KNS_ItemType": Table(incremental=False),
}


def scope(table: str, settings: Settings) -> str | None:
    """The table's scope filter with the configured Knesset / date filled in."""
    where = TABLES[table].where
    return where.format(**asdict(settings)) if where else None


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
# (seen: 473, 481) for a few seconds. Retry those like rate limits (429) and server errors.
RETRY_STATUS = (429, *range(470, 500), *range(500, 600))

Row = dict[str, Any]
GetJson = Callable[[str, dict[str, str]], dict[str, Any]]  # (path, params) -> JSON body


class Api:
    """HTTP access to the OData API, with retries and backoff from the settings."""

    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.base_url
        self.session = Client(
            request_timeout=settings.request_timeout,
            status_codes=RETRY_STATUS,
            request_max_attempts=settings.request_max_attempts,
            request_backoff_factor=settings.request_backoff_factor,
        ).session
        self.session.hooks["response"].append(self._log_errors)

    @staticmethod
    def _log_errors(response: Any, *args: Any, **kwargs: Any) -> None:
        """Log every failed response, including those that are retried."""
        if response.status_code >= 400:
            retry = "retrying" if response.status_code in RETRY_STATUS else "giving up"
            log.warning("HTTP %s, %s: %s", response.status_code, retry, response.url)

    def json(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        response = self.session.get(self.base_url + path, params=params)
        response.raise_for_status()
        return decode(path, response.content)

    def metadata(self) -> bytes:
        """The `$metadata` XML: every table with its typed columns."""
        response = self.session.get(self.base_url + "$metadata")
        response.raise_for_status()
        return response.content


class EmptyResponse(Exception):
    """The API answered 200 with no body: its server timed out (seen after exactly 30 s)."""


def decode(path: str, body: bytes) -> dict[str, Any]:
    """Parse a JSON body; an empty one means the API's server gave up on the query."""
    if not body.strip():
        raise EmptyResponse(f"{path}: the API returned an empty response (a server-side timeout)")
    return json.loads(body)


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


def api_count(get: GetJson, table: str, where: str | None = None) -> int:
    """Number of rows the API has for a table in our scope."""
    params = params_for(build_filter(where), **{"$count": "true", "$top": "0"})
    return get(table, params)["@odata.count"]


def edge_id(
    get: GetJson, table: str, where: str | None, since: datetime | None, last: bool
) -> int | None:
    """Smallest (or with `last`, largest) Id matching the filter; None if no rows."""
    order = "Id desc" if last else "Id"
    extra = {"$select": "Id", "$orderby": order, "$top": "1"}
    rows = get(table, params_for(build_filter(where, since), **extra))["value"]
    return rows[0]["Id"] if rows else None


def id_ranges(low: int, high: int, parts: int) -> list[tuple[int, int]]:
    """Split the Ids in (low, high] into `parts` ranges of (after, upto]."""
    step = -(-(high - low) // parts)  # ceiling division
    return [(start, min(start + step, high)) for start in range(low, high, step)]


def clean_page(table: str, page: list[Row], after: int) -> list[Row]:
    """Check a page and drop repeated Ids.

    Every row needs an Id, in increasing order after the previous page, or we raise:
    that would mean paging is broken. The API does repeat some Ids (seen: the same vote
    3 times); exact copies are dropped, and if copies differ the first is kept. Both logged.
    """
    rows: list[Row] = []
    previous = after
    for row in page:
        row_id = row.get("Id")
        if not isinstance(row_id, int) or row_id < previous or (row_id == previous and not rows):
            raise ValueError(f"{table}: bad or out-of-order Id {row_id!r} after {previous}")
        if row_id == previous:
            same = row == rows[-1]
            log.warning("%s: Id %s repeated by the API (%s copy dropped)", table, row_id,
                        "identical" if same else "DIFFERENT")  # fmt: skip
            continue
        rows.append(row)
        previous = row_id
    return rows


def fetch_range(
    get: GetJson,
    table: str,
    where: str | None,
    since: datetime | None,
    after: int,
    upto: int,
    select: str | None = None,
) -> Iterator[list[Row]]:
    """Pages of rows with `after < Id <= upto`, 100 at a time, ordered by Id.

    We page with `Id gt <last id>` instead of following `@odata.nextLink`:
    the API's next links use `$skip`, which gets slower the deeper you go
    (15s+ per page on the 2M-row vote table), while keyset paging stays ~1s.
    """
    last = after
    while True:
        extra = {"$orderby": "Id", **({"$select": select} if select else {})}
        page = get(table, params_for(build_filter(where, since, last, upto), **extra))["value"]
        if not page:
            return
        yield (rows := clean_page(table, page, last))
        last = rows[-1]["Id"]


def merge_pages(iterators: list[Iterator[list[Row]]]) -> Iterator[list[Row]]:
    """Run page iterators in parallel threads and yield their pages as they arrive.

    If the consumer stops early (an error, or the sample limit), every thread stops
    too: `put` gives up once `stop` is set, so no thread can block forever.
    """
    pages: queue.Queue = queue.Queue(maxsize=2 * len(iterators))
    stop = threading.Event()
    done = object()

    def put(item: object) -> bool:
        """Queue an item; False if the consumer has stopped."""
        while not stop.is_set():
            try:
                pages.put(item, timeout=0.5)
                return True
            except queue.Full:
                continue
        return False

    def drain(pages_of_range: Iterator[list[Row]]) -> None:
        try:
            for page in pages_of_range:
                if not put(page):
                    return
            put(done)
        except Exception as error:  # hand the error to the consumer, which re-raises it
            put(error)

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
            stop.set()


def fetch_table(
    get: GetJson,
    table: str,
    where: str | None = None,
    since: datetime | None = None,
    select: str | None = None,
    workers: int = 1,
    rows_per_range: int = 20_000,
) -> Iterator[list[Row]]:
    """All pages of a table. Large tables are split into Id ranges fetched in parallel."""
    low = edge_id(get, table, where, since, last=False)
    if low is None:
        return
    high = edge_id(get, table, where, since, last=True)
    parts = max(1, min(workers, (high - low) // rows_per_range))
    ranges = id_ranges(low - 1, high, parts)
    iterators = [fetch_range(get, table, where, since, a, b, select) for a, b in ranges]
    yield from iterators[0] if parts == 1 else merge_pages(iterators)


def parse_row(row: Row) -> Row:
    """Turn `LastUpdatedDate` into a datetime so dlt can compare it across time zones."""
    if row.get("LastUpdatedDate"):
        row["LastUpdatedDate"] = datetime.fromisoformat(row["LastUpdatedDate"])
    return row


def table_rows(
    get: GetJson,
    table: str,
    where: str | None,
    workers: int,
    rows_per_range: int,
    updated: dlt.sources.incremental[datetime] | None = None,
) -> Iterator[list[Row]]:
    """Rows of one table; with `updated`, only rows changed since the last run (minus the lag)."""
    since = updated.start_value if updated is not None else None
    for page in fetch_table(get, table, where, since, None, workers, rows_per_range):
        yield [parse_row(row) for row in page]


def table_resource(
    name: str, metadata: bytes, settings: Settings, get: GetJson, workers: int
) -> DltResource:
    """The dlt resource for one table.

    Incremental tables use SCD2: bronze keeps every version of a row, with
    `_dlt_valid_from` / `_dlt_valid_to`; the current version has `_dlt_valid_to` null.
    Rows that did not change produce the same row hash, so reruns add nothing.
    """
    table = TABLES[name]
    if table.incremental:
        disposition: Any = {"disposition": "merge", "strategy": "scd2"}
        lag = settings.lag_seconds
        updated = dlt.sources.incremental[datetime]("LastUpdatedDate", lag=lag)
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
    return resource(get, name, scope(name, settings), workers, settings.rows_per_range, updated)


@dlt.source(name="knesset_odata", max_table_nesting=0)
def knesset_odata(
    settings: Settings, api: Api, metadata: bytes, workers: int, tables: list[str]
) -> list[DltResource]:
    """The Knesset OData source: one resource (bronze table) per OData table."""
    return [table_resource(name, metadata, settings, api.json, workers) for name in tables]
