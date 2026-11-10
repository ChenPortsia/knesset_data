from datetime import datetime, timedelta, timezone

import pytest

from ingestion.odata import (
    TABLES,
    build_filter,
    fetch_pages,
    knesset_odata,
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


def test_build_filter_first_full_load():
    assert build_filter(0, None) == "Id gt 0"


def test_build_filter_incremental():
    since = datetime(2026, 11, 1, 8, 30, tzinfo=timezone(timedelta(hours=2)))
    assert (
        build_filter(42, since=since) == "Id gt 42 and LastUpdatedDate ge 2026-11-01T08:30:00+02:00"
    )


def test_build_filter_with_scope():
    assert build_filter(0, "KnessetNum ge 20") == "Id gt 0 and KnessetNum ge 20"


def test_fetch_pages_uses_last_id_of_each_page():
    pages = [[{"Id": 1}, {"Id": 2}], [{"Id": 5}], []]
    calls = []

    def fake_get(url, params):
        calls.append(params["$filter"])
        return {"value": pages[len(calls) - 1]}

    assert list(fetch_pages("KNS_Person", get=fake_get)) == pages[:2]
    assert calls == ["Id gt 0", "Id gt 2", "Id gt 5"]


def test_parse_row_compares_across_time_zones():
    winter = parse_row({"LastUpdatedDate": "2020-03-23T23:33:55.387+02:00"})
    summer = parse_row({"LastUpdatedDate": "2024-07-28T21:41:35.37+03:00"})
    assert winter["LastUpdatedDate"] < summer["LastUpdatedDate"]


def test_parse_row_keeps_missing_date():
    assert parse_row({"Id": 1}) == {"Id": 1}


def test_source_has_one_resource_per_table():
    assert set(knesset_odata().resources) == set(TABLES)


def test_sample_source_is_limited():
    source = knesset_odata(["KNS_Person"], max_pages=2)
    assert source.resources["KNS_Person"].limit is not None


def test_table_columns_from_metadata():
    assert table_columns(METADATA, "KNS_Person") == {
        "Id": {"data_type": "bigint", "nullable": True},
        "Email": {"data_type": "text", "nullable": True},
        "LastUpdatedDate": {"data_type": "timestamp", "nullable": True},
    }


def test_table_columns_unknown_table():
    with pytest.raises(KeyError):
        table_columns(METADATA, "KNS_Missing")
