"""Open DuckDB's built-in UI in the browser, with every database attached read-only.

    make ui      then query e.g.  SELECT * FROM warehouse.gold.dim_bill LIMIT 10

DuckDB allows one writer or many readers per file, so close this before make ingest / make dbt.
"""

from pathlib import Path

import duckdb

DATA = Path(__file__).resolve().parents[1] / "data"
FILES = {
    "raw": DATA / "raw" / "raw.duckdb",
    "warehouse": DATA / "warehouse" / "warehouse.duckdb",
    "published": DATA / "published" / "knesset.duckdb",
}

con = duckdb.connect()
for name, path in FILES.items():
    if path.exists():
        con.execute(f"ATTACH '{path}' AS {name} (READ_ONLY)")
        print(f"attached {name}")
con.execute("CALL start_ui()")
input("The UI is open at http://localhost:4213 . Press Enter here to close it.\n")
