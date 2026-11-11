import re
from datetime import datetime, timedelta, timezone

import pytest

from ingestion import odata
from ingestion.odata import (
    build_filter,
    clean_page,
    fetch_range,
    fetch_table,
    id_ranges,
    merge_pages,
    parse_row,
    table_columns,
)

METADATA = b"""<edmx:Edmx xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx"><edmx:DataServices>
<Schema xmlns="http://docs.oasis-open.org/odata/ns/edm"><EntityType Name="KNS_Person">
<Key><PropertyRef Name="Id"/></Key>
<Property Name="Id" Type="Edm.Int32" Nullable="false"/>
<Property Name="Email" Type="Edm.String"/>
<Property Name="LastUpdatedDate" Type="Edm.DateTimeOffset"/>
</EntityType></Schema></edmx:DataServices></edmx:Edmx>"""


def fake_api(ids: list[int]):
    """A tiny fake OData API over a list of Ids: Id filters, $orderby, $top, 100-row pages."""

    def get(url, params):
        filter_ = params.get("$filter", "")
        after = re.search(r"Id gt (\d+)", filter_)
        upto = re.search(r"Id le (\d+)", filter_)
        rows = [
            i
            for i in sorted(ids, reverse=params.get("$orderby") == "Id desc")
            if (not after or i > int(after.group(1))) and (not upto or i <= int(upto.group(1)))
        ]
        return {"value": [{"Id": i} for i in rows[: int(params.get("$top", 100))]]}

    return get


def test_build_filter():
    since = datetime(2026, 11, 1, 8, 30, tzinfo=timezone(timedelta(hours=2)))
    assert build_filter() is None
    assert build_filter("KnessetNum ge 20") == "KnessetNum ge 20"
    assert build_filter("KnessetNum ge 20", since, after=5, upto=9) == (
        "Id gt 5 and Id le 9 and KnessetNum ge 20 and LastUpdatedDate ge 2026-11-01T08:30:00+02:00"
    )


def test_id_ranges_cover_all_ids_once():
    assert id_ranges(0, 10, 3) == [(0, 4), (4, 8), (8, 10)]
    assert id_ranges(4, 5, 8) == [(4, 5)]


def test_clean_page_rejects_missing_or_unordered_ids():
    assert clean_page("T", [{"Id": 3}, {"Id": 7}], after=2) == [{"Id": 3}, {"Id": 7}]
    with pytest.raises(ValueError):
        clean_page("T", [{"Id": 3}, {"Id": 2}], after=0)
    with pytest.raises(ValueError):
        clean_page("T", [{"Id": 2}], after=2)
    with pytest.raises(ValueError):
        clean_page("T", [{"Name": "no id"}], after=0)


def test_clean_page_drops_ids_the_api_repeats():
    """The API returned vote 37161 three times; we keep the first copy."""
    page = [{"Id": 1, "v": "a"}, {"Id": 1, "v": "a"}, {"Id": 1, "v": "b"}, {"Id": 2, "v": "c"}]
    assert clean_page("T", page, after=0) == [{"Id": 1, "v": "a"}, {"Id": 2, "v": "c"}]


def test_fetch_range_pages_by_last_id():
    pages = list(fetch_range(fake_api(list(range(1, 301))), "T", None, None, after=0, upto=250))
    assert [len(p) for p in pages] == [100, 100, 50]
    assert pages[-1][-1]["Id"] == 250


def test_fetch_table_in_parallel_returns_every_row_once():
    ids = list(range(1, 3000, 2))  # 1500 rows with gaps
    pages = fetch_table(fake_api(ids), "T", workers=4, rows_per_range=300)
    assert sorted(r["Id"] for page in pages for r in page) == ids


def test_fetch_table_empty():
    assert list(fetch_table(fake_api([]), "T")) == []


def test_merge_pages_raises_errors_from_threads():
    def broken():
        yield [{"Id": 1}]
        raise RuntimeError("API down")

    with pytest.raises(RuntimeError, match="API down"):
        list(merge_pages([broken(), iter([[{"Id": 2}]])]))


def endless():
    while True:
        yield [{"Id": 1}]


@pytest.mark.timeout(10)
def test_merge_pages_stops_all_threads_after_an_error():
    """Regression: busy threads used to block forever once the consumer had stopped."""

    def broken():
        raise RuntimeError("API down")
        yield

    with pytest.raises(RuntimeError, match="API down"):
        list(merge_pages([broken(), endless(), endless(), endless()]))


@pytest.mark.timeout(10)
def test_merge_pages_stops_all_threads_when_consumer_stops_early():
    pages = merge_pages([endless(), endless()])
    assert next(pages) == [{"Id": 1}]
    pages.close()  # what dlt's sample limit does


def test_parse_row_compares_across_time_zones():
    winter = parse_row({"LastUpdatedDate": "2020-03-23T23:33:55.387+02:00"})
    summer = parse_row({"LastUpdatedDate": "2024-07-28T21:41:35.37+03:00"})
    assert winter["LastUpdatedDate"] < summer["LastUpdatedDate"]
    assert parse_row({"Id": 1}) == {"Id": 1}


def test_table_columns_from_metadata():
    assert table_columns(METADATA, "KNS_Person") == {
        "Id": {"data_type": "bigint", "nullable": True},
        "Email": {"data_type": "text", "nullable": True},
        "LastUpdatedDate": {"data_type": "timestamp", "nullable": True},
    }
    with pytest.raises(KeyError):
        table_columns(METADATA, "KNS_Missing")


def test_firewall_codes_are_retried_but_real_client_errors_are_not():
    assert {429, 473, 481, 500, 503} <= set(odata.RETRY_STATUS)
    assert not {400, 401, 403, 404} & set(odata.RETRY_STATUS)


def test_settings_come_from_dlt_config_and_env(monkeypatch):
    settings = odata.load_settings()  # ingestion/.dlt/config.toml
    assert (settings.from_knesset, settings.workers) == (20, 8)
    assert odata.scope("KNS_Bill", settings) == "KnessetNum ge 20"
    assert odata.scope("KNS_Person", settings) is None
    monkeypatch.setenv("SOURCES__KNESSET_ODATA__FROM_KNESSET", "24")
    assert odata.scope("KNS_Bill", odata.load_settings()) == "KnessetNum ge 24"


def test_empty_api_response_gets_a_clear_error():
    """The API answers 200 with no body when its server times out (seen after 30 s)."""
    with pytest.raises(odata.EmptyResponse, match="server-side timeout"):
        odata.decode("KNS_PlenumVote", b"")
    assert odata.decode("KNS_Bill", b'{"value": []}') == {"value": []}
