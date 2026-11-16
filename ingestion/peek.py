"""Look inside the Knesset's own protocol documents, before building a pipeline for them.

    python -m ingestion.peek          (make peek-documents)

For each Knesset from the 20th on, takes one committee protocol and one plenum protocol
("דברי הכנסת") through the API's document tables, downloads the Word file, and writes
docs/document_peek.md: whether it is a real .docx, its paragraph styles with examples, and
the markers (<< דובר >> ...) found in it. This shows whether one parser can read every
year. Loads nothing.
"""

import html
import io
import re
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

from ingestion.odata import Api, load_settings

REPORT = Path(__file__).resolve().parents[1] / "docs" / "document_peek.md"
# document table -> (its session table, its session column, the kind that is the protocol)
SOURCES = {
    "KNS_DocumentCommitteeSession": ("KNS_CommitteeSession", "CommitteeSessionID", "פרוטוקול ועדה"),
    "KNS_DocumentPlenumSession": ("KNS_PlenumSession", "PlenumSessionID", "דברי הכנסת"),
}
KNESSETS = range(20, 27)
MARKER = re.compile(r"<<\s*([^<>]{1,25}?)\s*>>")
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


def describe(title: str, row: dict[str, Any], content: bytes) -> str:
    """One document's section of the report."""
    lines = [f"## {title}", "", f"`{row.get('FilePath')}`", "", f"Size: {len(content):,} bytes"]
    if not zipfile.is_zipfile(io.BytesIO(content)):
        return "\n".join([*lines, f"Not a .docx file. First bytes: {content[:60]!r}", ""])
    rows = [(style, html.unescape(text)) for style, text in paragraphs(content)]
    markers = Counter(m for _, text in rows for m in MARKER.findall(text)).most_common(12)
    colon = sum(text.endswith(":") and len(text) < 80 for _, text in rows)
    lines += [
        f"Paragraphs: {len(rows):,}",
        f"Short paragraphs ending with a colon: {colon:,}",
        f"Markers: {markers}",
        "",
        "Styles, with how many paragraphs and three examples from the middle of the document:",
        "",
        "```",
    ]
    for style, count in Counter(style for style, _ in rows).most_common():
        texts = [text for s, text in rows if s == style]
        middle = texts[len(texts) // 2 : len(texts) // 2 + 3]
        lines += [f"{style!s} ({count})"] + [f"    {text[:120]}" for text in middle]
    return "\n".join([*lines, "```", ""])


def one_protocol(api: Api, table: str, knesset: int) -> dict[str, Any] | None:
    """A protocol document of a session from the middle of a Knesset, or None."""
    session_table, session_column, kind = SOURCES[table]
    sessions = api.json(
        session_table,
        {
            "$filter": f"KnessetNum eq {knesset}",
            "$orderby": "Id desc",
            "$top": "100",
            "$skip": "40",
        },
    )["value"]
    for session in sessions:
        found = api.json(
            table,
            {
                "$filter": f"{session_column} eq {session['Id']} and GroupTypeDesc eq '{kind}' "
                "and ApplicationDesc eq 'DOC'",
                "$top": "1",
            },
        )["value"]
        if found:
            return found[0]
    return None


def main() -> None:
    api = Api(load_settings())
    sections = []
    for table in SOURCES:
        for knesset in KNESSETS:
            title = f"{table}, Knesset {knesset}"
            try:
                row = one_protocol(api, table, knesset)
                if row is None:
                    sections.append(f"## {title}\n\nNo protocol document found.\n")
                    continue
                response = api.session.get(row["FilePath"].replace("\\", "/"))
                response.raise_for_status()
                sections.append(describe(title, row, response.content))
            except Exception as error:
                sections.append(f"## {title}\n\nFailed: {type(error).__name__}: {error}\n")
            print(title, flush=True)
    REPORT.write_text("# A look inside Knesset documents\n\n" + "\n".join(sections), "utf-8")
    print(f"wrote {REPORT}")


if __name__ == "__main__":
    main()
