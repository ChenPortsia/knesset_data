"""Compile the dbt analyses and print each one's result.

Runs against data/warehouse/<target file> opened read-only, without raw.duckdb attached:
the analyses may only use gold tables, as the agent will.

Run from the repo root:
    make answers                       # milestone 1 questions, full load
    uv run python transformation/scripts/run_analyses.py --target sample --folder milestone_1
"""

import argparse
import subprocess
import sys
from pathlib import Path

import duckdb

PROJECT = Path(__file__).resolve().parents[1]
WAREHOUSES = {"dev": "warehouse.duckdb", "sample": "warehouse_sample.duckdb"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", choices=list(WAREHOUSES), default="dev")
    parser.add_argument("--folder", default="milestone_1", help="folder under analyses/")
    args = parser.parse_args()

    dbt = str(Path(sys.executable).parent / "dbt")
    subprocess.run(
        [dbt, "compile", "--profiles-dir", ".", "--target", args.target, "--quiet",
         "--select", f"path:analyses/{args.folder}"],
        cwd=PROJECT, check=True,
    )  # fmt: skip
    compiled = PROJECT / "target" / "compiled" / "knesset" / "analyses" / args.folder
    warehouse = PROJECT.parent / "data" / "warehouse" / WAREHOUSES[args.target]
    with duckdb.connect(str(warehouse), read_only=True) as con:
        for path in sorted(compiled.glob("*.sql")):
            sql = path.read_text()
            print(f"\n## {sql.splitlines()[0].removeprefix('-- ')}")
            print(con.sql(sql))


if __name__ == "__main__":
    main()
