# transformation (dbt)

Builds the warehouse from the raw bronze tables written by ingestion.
Reads `data/raw/raw.duckdb` read-only (attached as the `raw` database) and writes
`data/warehouse/warehouse.duckdb`. These are the conventions every model follows: the
best practices from dbt Labs' guides, adapted to this project, plus our own decisions.

## Layout

```
models/
  1_staging/        # silver: one view per source table, 1:1, no joins
    odata/          #   stg_odata__<entity>.sql, _odata__sources.yml, _odata__models.yml
  2_intermediate/   # silver: joins and business logic, by business area
    people/  votes/  legislation/  committees/
  3_mart/           # gold: the star schema the agent queries, by business area
    core/  people/  votes/  legislation/  committees/  plenum/  oversight/
seeds/              # small hand-made CSVs: code labels, status/position mappings, coalition overrides
macros/             # is_current(), local_time(), code_label(), generate_schema_name()
tests/              # singular tests: anomalies across models
analyses/           # SQL that is compiled but not built: milestone_1/, journalist/ questions
snapshots/          # unused: bronze already keeps every version of every row
scripts/            # generate_staging.py, run_analyses.py (dev tools, not in the image)
```

Folders are numbered so they sort in build order. Each folder groups YAML files as
`_<folder>__models.yml` (and `_<source>__sources.yml`), next to the models they describe.

## Layers

| Layer | Folder | Schema | Materialized | Job | Named |
| --- | --- | --- | --- | --- | --- |
| staging | `1_staging/<source>/` | silver | view | rename, cast, keep current rows, clean source codes, decode labels | `stg_<source>__<entity>` |
| intermediate | `2_intermediate/<area>/` | silver | view | re-grain, join, isolate complex logic | `int_<entities>_<verb>` |
| mart | `3_mart/<area>/` | gold | table | wide entities for consumers | `dim_<entity>`, `fct_<event>` |

- **Source-conformed to business-conformed.** Staging mirrors the source, one model per
  table. From intermediate on, models are grouped by business area, not by source.
- **The DAG narrows as it goes:** many narrow staging models become fewer, wider marts.
- **Only `gold` is for consumers** (the agent, dashboards). `silver` views read
  `raw.duckdb`, so they only work where dbt attaches it; gold tables are self-contained.
- **No business logic in staging; no joins in staging.** Staging only renames, casts and
  cleans, so every later model starts from the same clean columns.
- **Don't build the same concept twice.** One `dim_bill`, used by everyone. When a CTE is
  needed by a second model, it moves to its own intermediate model: e.g.
  `int_person_knesset_factions` (used by votes, coalition periods and queries) and
  `int_faction_vote_majorities` (used by loyalty and faction agreement).

## SQL style

- Keywords and functions in UPPERCASE, names in lowercase snake_case.
- Every output column is cast explicitly: `CAST(id AS INTEGER) AS bill_id`.
- Four-space indentation, trailing commas, `AS` written out for every alias.
- Every model starts with a comment stating what it is and its grain:
  `-- Grain: one row per vote and MK`.
- Every model is a chain of CTEs, always in this order:

```sql
WITH source AS (          -- import: read a source or upstream model, unchanged
    SELECT * FROM {{ source('odata', 'kns_bill') }}
),
renamed AS (              -- rename and cast; nothing else
    SELECT CAST(id AS INTEGER) AS bill_id, ...
    FROM source
),
filtered AS (             -- keep only the rows this model is about
    SELECT * FROM renamed
    WHERE {{ is_current('kns_bill', 'bill_id') }}
),
enhanced AS (             -- add derived columns and joins; cast every output column
    SELECT *, CAST(... AS VARCHAR) AS origin
    FROM filtered
)
SELECT *                  -- the last line selects from the final CTE
FROM enhanced
```

- Staging always has all four steps. In intermediate and mart models a step with nothing
  to do is left out (they rarely rename), and import CTEs are named after the model they
  read (`bills`, `vote_results`).
- Extra logic CTEs sit between `filtered` and `enhanced`, each doing one thing and named for
  it (`items_per_session`, `periods_collapsed`, `faction_majorities`).
- The final `SELECT * FROM <last CTE>` makes it easy to inspect any step while developing:
  point it at another CTE.
- Comments explain *why* (a source quirk, a rule), not what the SQL says.

## Joins

- Always write the join type: `LEFT JOIN` or `INNER JOIN`, never a bare `JOIN`. No `RIGHT JOIN`:
  swap the tables instead.
- Prefix every column with its full table or CTE name once a model joins (`bills.bill_id`),
  and no short aliases like `b.` or `v.`.
- **Never let a join multiply rows.** Aggregate the other side to the join key first
  (`initiators_per_bill`, `votes_per_bill`), and protect the grain with a primary-key test.
  If a join can still match several rows (overlapping periods), choose one explicitly with
  `QUALIFY ROW_NUMBER() ... = 1` and say why in a comment.
- `LEFT JOIN` when the left side's rows must all survive (the usual case in marts);
  `INNER JOIN` only when dropping unmatched rows is the point (scoping link tables).

## Seeds

Seeds are small CSVs kept in git and reviewed like code. Three kinds:

| Kind | Example | Rule |
| --- | --- | --- |
| Code labels | `code_labels` | English label for a source code; a code without a label fails a test |
| Mappings | `bill_status_stages`, `position_roles` | source code -> our concept (stage, reading, role); include the source's Hebrew so a reviewer can check the mapping |
| Overrides | `coalition_overrides` | corrections to a rule derived from data; every row has a `reason` |

- Seeds are always recreated (`+full_refresh: true`), so adding a column just works.
- A hand-made seed says so in its description, and what to do when the source changes.

## Derived facts

Some facts the source doesn't record are derived from the data, by a rule that is written in
the model's header comment, with known exceptions in an override seed. The pattern:

1. **Derive** with a simple, explainable rule (`int_coalition_periods_derived`: a faction is in the
   coalition while one of its MKs holds a government post).
2. **Correct** documented exceptions in a seed with a reason per row (`coalition_overrides`:
   Ra'am, Yamina, Shas), applied in a separate model (`int_coalition_periods`).
3. **Record the source** of every row (`source`: `government_posts` or `override`), so a consumer
   knows which rows are rules and which are corrections.
4. **Check the result against reality** with an analysis: a coalition faction voting with the
   opposition, or the reverse, points to a missing exception (that's how Shas was found).

The same applies to `faction_match` on votes (`dated`, `knesset` or `none`): whenever a
fallback rule fills a gap, a column says which rule was used.

## Keys and grain

- Source IDs are stable integers, so dimensions use them as keys (`bill_id`, `person_id`)
  instead of surrogate keys. Our dimensions keep current values only (type 1); history
  lives in bronze (every version of every row) and in dated facts like
  `fct_faction_membership`.
- Where a model's grain has no source ID, the key is an MD5 hash of the grain columns
  (`session_bill_id`, `membership_id`).
- Every fact joins to `dim_date` through a `DATE` column (`vote_date`, `session_date`).
- Keys are named `<entity>_id` everywhere, so the same column means the same thing in
  every model.

## Naming

- Columns: `<entity>_id` for keys, `is_` / `was_` for booleans, `_at` for timestamps (Israel
  local time unless noted), `_date` for dates, `_he` / `_en` for the Hebrew and English
  version of a label, plural nouns for counts (`initiators`, `votes_for`).
- Times are converted to Israel local time in staging (`local_time()`), so a vote at 01:45
  falls on the right day. `updated_at` and `loaded_at` stay in UTC (`TIMESTAMPTZ`).
- Hebrew text stays as the source has it; English labels come from seeds.

## Source quirks handled in staging

| Quirk | Where handled |
| --- | --- |
| Every version of every row in bronze (SCD2) | `is_current()` keeps the current version |
| Rows deleted in the API | `is_current()` leaves out ids in `bronze.deleted_ids` |
| UTC timestamps vs the Knesset calendar | `local_time()` |
| Numeric codes with Hebrew text only | `code_label()` adds English labels from `seeds/code_labels.csv` |
| `-1` meaning "none" (`kns_bill.committee_id`, `kns_committee.additional_type_id`) | `NULLIF(..., -1)` |
| 0/1 integers used as booleans (`is_discussion`) | cast to `BOOLEAN` |

Quirks handled later, because they need joins:

| Quirk | Where handled |
| --- | --- |
| Link tables (initiators, session items) load for all Knessets | intermediate joins them to in-scope parents |
| A chair and a member row for the same faction period | `int_faction_memberships_collapsed` merges overlapping periods |
| The source rewrote most 25th-Knesset membership dates on 2026-11-04 | votes and queries fall back to the MK's only faction in that Knesset (`int_person_knesset_factions`); `faction_match` says which rule matched |
| Posts are re-issued when a new Knesset starts | `int_person_roles_classified` starts a new period per Knesset, so a post belongs to the MK's faction in that Knesset |
| The same role repeated with different end dates | `int_person_roles_classified` merges overlapping rows of the same role |
| No table says which factions are in the coalition | derived from government posts, with `coalition_overrides` (see Derived facts) |
| Readings are not recorded per bill | `int_bill_plenum_readings`: the bill's status on the plenum agenda, mapped to a reading in `bill_status_stages` |

## Tests

Each layer tests what it adds, not what it passes through (dbt Labs, "Test smarter").

- **staging:** the primary key of every model; decoded codes (a new code without a label fails).
- **intermediate:** the grain wherever it changes or is enriched; `accepted_values` on new
  categorical columns (stage, outcome, faction_match).
- **mart:** primary keys, `relationships` from every fact to its dimensions, and
  `accepted_values` on categorical columns.
- **anomalies** (`tests/`, singular SQL): overlapping faction periods, votes without a faction,
  bill statuses without a stage.
- **Severity:** `error` when the model is wrong; `warn` when the data is unusual but the model
  is right, e.g. a known source gap. Every `warn` has a comment saying why it is expected.
  Known warnings today: faction overlaps (formal splits and the 2026 election handover),
  committee discussions and one vote about bills from before the 20th Knesset, and 95 vote
  results whose 2 votes are missing from the API.
- **On the sample target, relationship tests warn instead of failing:** the sample holds 200
  rows per table, so its foreign keys can point outside it. Every other test keeps its
  severity on both targets.
- Don't test what a model guarantees itself: if `filtered` removes nulls, a `not_null`
  test on that column adds nothing.

## Contracts

Every gold model has an enforced contract (`contract: {enforced: true}`): its YAML lists
every column with its `data_type`, and dbt refuses to build the model if the SQL's output
differs. Consumers (the agent) can rely on gold's columns and types never changing silently.
Changing a gold column means changing its YAML in the same commit. To see a model's output
types before writing the YAML, compile it (`dbt compile --select <model>`) and run
`DESCRIBE (<compiled SQL>)` in DuckDB.

## Analyses

`analyses/` holds questions answered in SQL against gold only, compiled by dbt so they
always use the current model names, and never built as tables:

- `milestone_1/`: the 10 questions that define milestone 1 (`make answers`).
- `journalist/`: questions from `docs/questions.md`'s journalist question bank, J1–J7.

Run a folder with `uv run python transformation/scripts/run_analyses.py --folder <folder>`.
It opens the warehouse read-only without `raw.duckdb`, which proves the answer needs gold only.
Analyses are also the check that a derived model matches reality.

## Documentation

- Every model and every column has a description as `English | Hebrew`. The context layer
  (milestone 2) is built from these.
- A model's description ends with its grain: `Grain: one row per ...`.
- Hand-made seeds say so in their description, and what to do when the source changes.
- Browse everything with `make docs` (or `make docs TARGET=sample`).

## Variables

| Variable | Default | Meaning |
| --- | --- | --- |
| `from_knesset` | 20 | First Knesset in scope; keep in step with `ingestion/.dlt/config.toml` |
| `vote_id` | none | The vote for `analyses/milestone_1/q05_*` |

## Staging models are generated

The 20 OData staging models and their YAML are written by `scripts/generate_staging.py`
from one spec (columns, English | Hebrew descriptions, derived columns, `-1` codes) and the
API's `$metadata` (column types). To change a staging model, edit the spec and run
`make staging-models`; `git diff` then shows exactly what changed. Intermediate and mart
models are written by hand.

## Run

From the repo root:

```bash
make dbt                 # build and test everything (TARGET=sample for the test load)
make answers             # answer the milestone 1 questions from gold
make docs                # browse model and column docs
make staging-models      # regenerate the staging models
```

Or `POST /builds` on the transformation service (see the main README). Run dbt after an
ingestion run has finished: DuckDB allows one writer per file.
