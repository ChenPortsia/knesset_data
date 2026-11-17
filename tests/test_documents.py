"""The documents pipeline: reading a protocol's paragraphs and choosing what to download."""

import io
import zipfile

import duckdb
import pytest

from ingestion.documents import fetch, read_paragraphs, to_rows, wanted

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def docx(chair_id: str = "af6") -> bytes:
    """A tiny protocol: the chair's style has a different id in different files."""
    styles = (
        f"<w:styles {W}>"
        f'<w:style w:styleId="{chair_id}"><w:name w:val="יור"/></w:style>'
        '<w:style w:styleId="a4"><w:name w:val="דובר"/></w:style>'
        "</w:styles>"
    )
    document = (
        f"<w:document {W}><w:body>"
        f'<w:p><w:pPr><w:pStyle w:val="{chair_id}"/></w:pPr>'
        '<w:r><w:t>&lt;&lt; יור &gt;&gt; היו"ר משה גפני: &lt;&lt; יור &gt;&gt;</w:t></w:r></w:p>'
        "<w:p><w:r><w:t>בוקר</w:t></w:r><w:r><w:tab/><w:t>טוב.</w:t></w:r></w:p>"
        "<w:p><w:r><w:t> </w:t></w:r></w:p>"
        '<w:p><w:pPr><w:pStyle w:val="a4"/></w:pPr><w:r><w:t>נאור שירי (יש עתיד):</w:t></w:r></w:p>'
        "<w:p><w:r><w:t>תודה.</w:t></w:r></w:p>"
        "</w:body></w:document>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", document)
        archive.writestr("word/styles.xml", styles)
    return buffer.getvalue()


def test_paragraphs_carry_the_style_name_whatever_its_id_in_the_file():
    expected = [
        ("יור", '<< יור >> היו"ר משה גפני: << יור >>'),
        (None, "בוקר טוב."),
        ("דובר", "נאור שירי (יש עתיד):"),
        (None, "תודה."),
    ]
    assert read_paragraphs(docx("af6")) == expected
    assert read_paragraphs(docx("af7")) == expected


def test_a_file_in_the_old_word_format_is_recorded_but_not_read():
    assert read_paragraphs(b"\xd0\xcf\x11\xe0 old binary") is None
    rows = to_rows({"document_id": 5, "session_id": 1, "kind": "plenum", "file_path": "x"}, b"old")
    assert rows["protocol_documents"][0]["is_docx"] is False
    assert rows["protocol_paragraphs"] == []


def test_a_document_becomes_one_summary_row_and_a_row_per_paragraph():
    document = {"document_id": 5, "session_id": 1, "kind": "committee", "file_path": "x"}
    rows = to_rows(document, docx())
    assert rows["protocol_documents"] == [
        document | {"bytes": len(docx()), "is_docx": True, "paragraphs": 4, "speaker_paragraphs": 2}
    ]
    assert rows["protocol_paragraphs"][2] == {
        "document_id": 5, "paragraph_index": 2, "style": "דובר",
        "paragraph_text": "נאור שירי (יש עתיד):",
    }  # fmt: skip


def test_a_document_that_fails_to_download_is_skipped_not_fatal():
    def broken(url: str) -> bytes:
        raise OSError("access denied")

    assert fetch(broken, {"document_id": 5, "file_path": "https://x/y.doc"}) is None


@pytest.fixture
def raw():
    con = duckdb.connect()
    con.execute(
        """
        CREATE SCHEMA bronze;
        CREATE TABLE bronze.kns_committee_session AS SELECT * FROM (VALUES
            (1, 25, 4198, TIMESTAMPTZ '2024-02-13 10:00:00+02', NULL),
            (2, 25, 4198, TIMESTAMPTZ '2024-03-01 10:00:00+02', NULL),
            (3, 25, 9999, TIMESTAMPTZ '2024-03-01 10:00:00+02', NULL),
            (4, 24, 4198, TIMESTAMPTZ '2022-03-01 10:00:00+02', NULL)
        ) AS t (id, knesset_num, committee_id, start_date, _dlt_valid_to);
        CREATE TABLE bronze.kns_document_committee_session AS SELECT * FROM (VALUES
            (10, 1, 'פרוטוקול ועדה', 'DOC', 'https://fs/1_old.doc', NULL),
            (11, 1, 'פרוטוקול ועדה', 'DOC', 'https://fs/1_new.doc', NULL),
            (12, 1, 'פרוטוקול ועדה', 'PDF', 'https://fs/1.pdf', NULL),
            (13, 1, 'התייחסות בעקבות הדיון', 'DOC', 'https://fs/1_reply.doc', NULL),
            (20, 2, 'פרוטוקול ועדה', 'DOC', 'https://fs/2.doc', NULL),
            (30, 3, 'פרוטוקול ועדה', 'DOC', 'https://fs/3.doc', NULL),
            (40, 4, 'פרוטוקול ועדה', 'DOC', 'https://fs/4.doc', NULL),
            (50, 99, 'פרוטוקול ועדה', 'DOC', 'https://fs/unknown_session.doc', NULL)
        ) AS t (id, committee_session_id, group_type_desc, application_desc, file_path,
                _dlt_valid_to);
        CREATE TABLE bronze.protocol_documents AS SELECT 20 AS document_id;
        """
    )
    return con


def test_one_protocol_per_known_session_the_newest_word_file_not_loaded_yet(raw):
    todo, counts = wanted(raw, "committee")
    # session 1: the newest Word protocol (not the PDF, not the reply); 2 is loaded; 99 unknown
    assert [d["document_id"] for d in todo] == [11, 30, 40]
    assert todo[0] == {
        "document_id": 11, "session_id": 1, "kind": "committee",
        "file_path": "https://fs/1_new.doc",
    }  # fmt: skip
    assert counts == {"sessions_with_a_protocol": 4, "already_loaded": 1, "to_load": 3}


def test_filters_choose_a_slice(raw):
    def ids(**filters):
        return [d["document_id"] for d in wanted(raw, "committee", **filters)[0]]

    assert ids(knesset=24) == [40]
    assert ids(year=2024, committee_id=4198) == [11]
    assert ids(limit=2) == [11, 30]
