"""Reading a Knesset protocol document: paragraphs with their styles."""

import io
import zipfile

from ingestion.peek import describe, paragraphs

XML = (
    '<w:document xmlns:w="x"><w:body>'
    '<w:p><w:pPr><w:pStyle w:val="af6"/></w:pPr><w:r><w:t>היו"ר משה גפני:</w:t></w:r></w:p>'
    "<w:p><w:r><w:t>בוקר </w:t></w:r><w:r><w:t>טוב.</w:t></w:r></w:p>"
    "<w:p><w:r><w:t> </w:t></w:r></w:p>"
    "</w:body></w:document>"
)


def docx() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", XML)
    return buffer.getvalue()


def test_paragraphs_keep_their_style_and_join_their_runs():
    assert paragraphs(docx()) == [("af6", 'היו"ר משה גפני:'), (None, "בוקר טוב.")]


def test_a_file_that_is_not_a_docx_is_said_so():
    assert "Not a .docx file" in describe("KNS_DocumentPlenumSession", {"Id": 1}, b"\xd0\xcf old")
    assert "Short lines ending with a colon: 1" in describe("t", {"Id": 1}, docx())
