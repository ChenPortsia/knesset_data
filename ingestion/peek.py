"""Look inside the Knesset's own protocol documents, before building a pipeline for them.

    python -m ingestion.peek          (make peek-documents)

Finds the newest committee protocol and the newest plenum protocol ("דברי הכנסת") through
the API's document tables, downloads each Word file, and writes docs/document_peek.md:
whether it is a real .docx, its paragraph styles, and the paragraphs around the first
speakers. Loads nothing.
"""

import io
import re
import zipfile
from collections import Counter
from pathlib import Path

from ingestion.odata import Api, load_settings

REPORT = Path(__file__).resolve().parents[1] / "docs" / "document_peek.md"
KINDS = {  # table -> the kind of document that is the protocol
    "KNS_DocumentCommitteeSession": "פרוטוקול ועדה",
    "KNS_DocumentPlenumSession": "דברי הכנסת",
}
PARAGRAPH = re.compile(r"<w:p[ >].*?</w:p>", re.S)
STYLE = re.compile(r'<w:pStyle w:val="([^"]+)"')
TEXT = re.compile(r"<w:t[^>]*>([^<]*)</w:t>")


def paragraphs(docx: bytes) -> list[tuple[str | None, str]]:
    """(style, text) of each non-empty paragraph of a .docx file."""
    xml = zipfile.ZipFile(io.BytesIO(docx)).read("word/document.xml").decode("utf-8")
    found = []
    for paragraph in PARAGRAPH.findall(xml):
        text = "".join(TEXT.findall(paragraph)).strip()
        if text:
            style = STYLE.search(paragraph)
            found.append((style.group(1) if style else None, text))
    return found


def describe(table: str, row: dict, content: bytes) -> str:
    """One document's section of the report."""
    lines = [f"## {table}", "", "```json", str(row), "```", "", f"Size: {len(content):,} bytes"]
    if not zipfile.is_zipfile(io.BytesIO(content)):
        return "\n".join([*lines, f"Not a .docx file. First bytes: {content[:80]!r}", ""])
    rows = paragraphs(content)
    styles = Counter(style for style, _ in rows).most_common()
    lines += [f"Paragraphs: {len(rows):,}", "", f"Styles: {styles}", ""]
    # A speaker line is short and ends with a colon; show what surrounds the first few
    speakers = [i for i, (_, text) in enumerate(rows) if text.endswith(":") and len(text) < 80]
    lines += [f"Short lines ending with a colon: {len(speakers):,}", ""]
    for start in speakers[40:43] or speakers[:3]:
        lines += ["```"] + [f"{s!s:8} {t[:110]}" for s, t in rows[start : start + 4]] + ["```", ""]
    lines += ["First 25 paragraphs:", "", "```"]
    lines += [f"{s!s:8} {t[:110]}" for s, t in rows[:25]] + ["```", ""]
    return "\n".join(lines)


def main() -> None:
    api = Api(load_settings())
    sections = []
    for table, kind in KINDS.items():
        row = api.json(
            table,
            {
                "$filter": f"GroupTypeDesc eq '{kind}' and ApplicationDesc eq 'DOC'",
                "$orderby": "Id desc",
                "$top": "1",
            },
        )["value"][0]
        url = row["FilePath"].replace("\\", "/")
        print(f"{table}: {url}")
        response = api.session.get(url)
        response.raise_for_status()
        sections.append(describe(table, row, response.content))
    REPORT.write_text("# A look inside Knesset documents\n\n" + "\n".join(sections), "utf-8")
    print(f"wrote {REPORT}")


if __name__ == "__main__":
    main()
