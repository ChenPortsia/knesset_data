"""Ingestion: Knesset OData API -> data/raw/raw.duckdb, as a dlt project.

dlt reads its settings from ingestion/.dlt/ (config.toml, secrets.toml).
"""

import os
from pathlib import Path

os.environ.setdefault("DLT_PROJECT_DIR", str(Path(__file__).parent))
