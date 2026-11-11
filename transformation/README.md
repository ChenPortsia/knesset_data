# transformation (dbt)

Builds the warehouse from the raw bronze tables written by ingestion.
Reads `data/raw/raw.duckdb` read-only (as the `raw` database) and writes `data/warehouse/warehouse.duckdb`.

```
models/
  1_staging/       # silver: one view per source table, 1:1, no joins
    odata/         #   stg_odata__<entity>.sql, _odata__sources.yml, _odata__models.yml
  2_intermediate/  # silver: joins and business logic, grouped by business area
    people/        #   int_faction_memberships_collapsed
    votes/         #   int_votes_joined_to_items, int_vote_results_joined_to_factions
    legislation/   #   int_bills_joined_to_stages, int_bill_initiators_filtered
    committees/    #   int_committee_sessions_bridged_to_bills
  3_mart/          # gold: the star schema the agent queries (dim_*, fct_*, agg_*)
seeds/             # small CSVs: code labels, bill status -> stage (later: glossary, aliases)
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

- The steps always come in this order. In intermediate and mart models a step with nothing
  to do is left out (they rarely rename), and extra logic CTEs sit between `filtered` and
  `enhanced`, each named for the one thing it does (`items_per_session`, `periods_collapsed`).
- Joins: explicit type (`LEFT JOIN`, `INNER JOIN`), columns prefixed with the full table
  name (no `b.`/`v.` aliases), and aggregate to the other side's grain *before* joining, so a
  join can never multiply rows.
- Every model starts with a comment stating its grain: `-- Grain: one row per ...`.
- Every model and column has an `English | Hebrew` description in the model's YAML.

## Layers

| Layer | Folder | Schema | Materialized | Job |
| --- | --- | --- | --- | --- |
| staging | `1_staging/<source>/` | silver | view | one model per source table: rename, cast, keep current rows, decode codes |
| intermediate | `2_intermediate/<business area>/` | silver | view | re-grain, join, isolate complex logic; named `int_<entities>_<verb>` |
| mart | `3_mart/` | gold | table | the star schema the agent queries: `dim_*`, `fct_*`, `agg_*` |

Only `gold` is for consumers (the agent, dashboards). `silver` views read `raw.duckdb`, so they
work only where dbt attaches it.

## Tests

Following dbt Labs' guidance, each layer tests what it adds, not what it passes through:

- **staging:** primary keys, and decoded codes (a new code without a label fails).
- **intermediate:** the grain (primary key) wherever it changes or is enriched, and new
  columns (`accepted_values` on stages and outcomes).
- **anomalies** (`tests/`, severity `warn`): faction periods that overlap, votes without a
  faction, bill statuses without a stage. They flag data to look at; they don't stop a build.

## Run

From the repo root: `make dbt` (or `make dbt TARGET=sample`), or `POST /builds` on the transformation service.
