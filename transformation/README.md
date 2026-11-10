# transformation (dbt)

Builds the warehouse from the raw bronze tables written by ingestion.
Reads `data/raw.duckdb` read-only (as the `raw` database) and writes `data/warehouse.duckdb`.

```
models/
  1_staging/       # silver: one view per source table, 1:1, no joins
    odata/         #   stg_odata__<entity>.sql, _odata__sources.yml, _odata__models.yml
  2_intermediate/  # silver: joins and business logic (int_*)
  3_mart/          # gold: the star schema the agent queries (dim_*, fct_*, agg_*)
seeds/             # small CSVs: code labels (later: glossary, aliases)
macros/            # is_current(), local_time(), code_label(), generate_schema_name()
tests/             # custom SQL tests
analyses/          # ad-hoc SQL, compiled but not built
snapshots/         # (unused: bronze already keeps every version of every row)
scripts/           # generate_staging.py: writes the staging models (dev tool, not in the image)
```

## Staging models are generated

The 20 OData staging models and their YAML are written by `scripts/generate_staging.py`
from one spec (columns, English | Hebrew descriptions, derived columns) and the API's
`$metadata` (column types). To change a staging model, edit the spec and run:

```bash
make staging-models    # from the repo root; overwrites models/1_staging/odata/
```

Then `git diff` shows exactly what changed. Intermediate and mart models are written by hand.

## SQL style

- Keywords and functions in UPPERCASE, names in lowercase.
- Every column is cast explicitly: `CAST(id AS INTEGER) AS bill_id`.
- Every model is a chain of CTEs, in this order:

```sql
WITH source AS (        -- read the source or upstream model, unchanged
    SELECT * FROM {{ source('odata', 'kns_bill') }}
),
renamed AS (            -- rename and cast every column; nothing else
    SELECT CAST(id AS INTEGER) AS bill_id, ...
    FROM source
),
filtered AS (           -- keep only the rows this model is about
    SELECT * FROM renamed
    WHERE {{ is_current('kns_bill', 'bill_id') }}
),
enhanced AS (           -- add derived columns (labels, full names, flags)
    SELECT *, CAST(... AS VARCHAR) AS origin
    FROM filtered
)
SELECT * EXCLUDE (valid_to)
FROM enhanced
```

- Every model and column has an `English | Hebrew` description in the model's YAML.

## Run

From the repo root: `make dbt` (or `make dbt TARGET=sample`), or `POST /builds` on the transformation service.
