"""The protocols pipeline: parsing the dataset's files and choosing what to load."""

import duckdb
import pytest

from ingestion.protocols import fetch_session, parse_session, read_manifest, wanted

MANIFEST = (
    "session_id,session_date,knesset_num,committee_name,words_count,duration\n"
    "10,2024-01-02 10:00:00,25,ועדת הכספים,120.0,60\n"
    "11,2024-03-05 10:00:00,25,ועדת הכספים,,60\n"
    "12,2023-03-05 10:00:00,25,ועדת הכספים,50.0,60\n"
    "13,2024-03-05 10:00:00,25,ועדת הכלכלה,50.0,60\n"
    "99,2024-03-05 10:00:00,25,ועדת הכספים,50.0,60\n"
)
FILES = {
    "raw.protocol.txt": "שלום לכולם. תודה.",
    "speakers.txt": '7\tהיו"ר משה גפני\n10000001\tנאור שירי (יש עתיד)\n',
    "speakers.segments.txt": "7\t0\t12\n10000001\t12\t17\n",
}


def test_the_manifest_keeps_our_columns_and_survives_empty_counts():
    rows = read_manifest(MANIFEST)
    assert rows[0] == {
        "session_id": 10, "session_date": "2024-01-02 10:00:00", "knesset_num": "25",
        "committee_name": "ועדת הכספים", "words_count": 120,
    }  # fmt: skip
    assert rows[1]["words_count"] is None


def test_a_session_becomes_rows_of_three_tables():
    rows = parse_session(10, FILES)
    assert rows["protocol_text"] == [{"session_id": 10, "text": FILES["raw.protocol.txt"],
                                      "characters": 17}]  # fmt: skip
    assert rows["protocol_speakers"][0] == {
        "session_id": 10, "speaker_id": 7, "speaker_name": 'היו"ר משה גפני'
    }  # fmt: skip
    assert rows["protocol_segments"][1] == {
        "session_id": 10, "segment_index": 1, "speaker_id": 10000001,
        "start_char": 12, "end_char": 17,
    }  # fmt: skip
    # the segments point into the text by character
    first = rows["protocol_segments"][0]
    assert FILES["raw.protocol.txt"][first["start_char"] : first["end_char"]] == "שלום לכולם. "


def test_a_session_that_fails_to_download_is_skipped_not_fatal():
    def broken(path: str) -> str:
        raise OSError("connection reset")

    assert fetch_session(broken, 10) is None


@pytest.fixture
def raw():
    con = duckdb.connect()
    con.execute(
        """
        CREATE SCHEMA bronze;
        CREATE TABLE bronze.kns_committee_session AS SELECT * FROM (VALUES (10), (11), (12), (13))
            AS t (id);
        CREATE TABLE bronze.protocol_text AS SELECT 10 AS session_id;
        """
    )
    return con


def test_only_known_sessions_of_the_slice_that_are_not_loaded_yet(raw):
    todo, counts = wanted(raw, read_manifest(MANIFEST), "ועדת הכספים", 2024, None)
    assert todo == [11]  # 10 is loaded, 12 is another year, 13 another committee, 99 unknown
    assert counts == {
        "in_dataset": 5, "chosen": 3, "unknown_session": 1, "already_loaded": 1, "to_load": 1
    }  # fmt: skip


def test_everything_is_chosen_without_filters_and_limit_caps_it(raw):
    assert wanted(raw, read_manifest(MANIFEST), None, None, None)[0] == [11, 12, 13]
    assert wanted(raw, read_manifest(MANIFEST), None, None, 2)[0] == [11, 12]
