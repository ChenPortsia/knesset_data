# context

What the agent reads before it touches data: what tables and columns mean, what
parliamentary terms mean in this data, how metrics are computed, what people call things,
how to read questions correctly, and SQL known to answer real questions.

**Git is the source of truth.** Every item is a few lines of YAML in this folder, changed
through a pull request and checked by CI. The `context` schema in the warehouse is rebuilt
from these files by `make context` and never edited by hand.

## What's here

| Folder | Kind | Example | Written |
| --- | --- | --- | --- |
| `glossary/` | parliamentary terms → where they are in the data | קריאה טרומית → `fct_bill_reading.reading = 'preliminary'` | by hand |
| `aliases/` | names people use → one entity | "ועדת חוץ" → the Foreign Affairs and Defense Committee | by hand |
| `rules/` | how to read questions and use the data | "this Knesset" means `dim_knesset.is_current` | by hand |
| `verified_queries/` | a question → SQL known to answer it → expected result | Q1: bills by origin, 25th Knesset | by hand |
| `expected/` | each verified query's approved result, as CSV | | by `make context-approve` |
| (tables, columns) | every gold table and column, with English and Hebrew descriptions | `dim_bill.is_passed` | generated from dbt |
| (metrics) | every MetricFlow metric | `bill_pass_rate` | generated from dbt |
| `schemas/` | JSON Schemas so editors can check the YAML | | by `make context-schemas` |
| `items.py` | the fields of each kind, and their rules | | by hand (code) |

Tables, columns and metrics are never written here: change their descriptions in the dbt
YAML (`transformation/models/3_mart/`) and they flow into the context.

## How to change the context

1. **Edit or add an item** in the right YAML file. Every file starts with a line that tells
   VS Code (with the YAML extension) which schema to use, so you get autocomplete and errors
   while typing.
2. **Check it** (seconds, no data needed):

   ```bash
   make context-check
   ```

3. **Check it against the data and load it:**

   ```bash
   make context
   ```

4. **Open a pull request.** CI runs `context check` again; a reviewer reads the diff.

### Add a glossary term

```yaml
- id: glossary.reservation            # glossary.<snake_case>, unique
  term_he: הסתייגות
  term_en: reservation (amendment)
  synonyms: [הסתייגויות]
  definition: >
    A proposed change to a bill's wording, voted on in the second reading.
  maps_to:                            # where it lives in gold
    - column: fct_plenum_vote.vote_subject
      value: הסתייגות                 # optional: one value of the column
```

### Add an alias

Each name may appear in only one alias, so a name always means one thing.

```yaml
- id: alias.person.rothman
  names: [רוטמן, שמחה רוטמן, Rothman]
  resolves_to: {column: dim_person.person_id, values: [<person_id>]}
```

### Add a rule

```yaml
- id: rule.recess
  title: The Knesset doesn't sit in recess
  rule: >
    Few sessions happen in the summer and winter recesses; compare activity month to month
    only within the same sitting.
  applies_to: [dim_date.month]
```

### Add a verified query

1. Write the SQL as a dbt analysis in `transformation/analyses/<folder>/<name>.sql`
   (gold models only, project SQL style).
2. Check its result by hand, then add the item:

   ```yaml
   - id: vq.laws_per_month
     question_en: How many laws passed each month?
     question_he: כמה חוקים עברו בכל חודש?
     sql_file: journalist/j08_laws_per_month.sql
     stable: false            # true only if the answer can't change and its order is fixed
     verified_by: chen
     verified_at: 2026-11-12
   ```

3. Store its result as the expected one, and commit the CSV with it:

   ```bash
   make context-approve ID=vq.laws_per_month
   ```

## What the checks catch

| Check | When | Example |
| --- | --- | --- |
| Fields and formats (`items.py`) | `make context-check`, CI | a misspelled field, an id without its kind prefix |
| Unique ids, and alias names in only one alias | `make context-check`, CI | "ועדת חוץ" in two aliases |
| References to gold models and columns | `make context-check`, CI | `dim_bill.passed` (it's `is_passed`), a silver model |
| `see_also` points to an item | `make context-check`, CI | a renamed rule |
| Mapped values and alias keys exist in the data | `make context` | `origin = 'privat'`, a person id that doesn't exist |
| Verified queries run and match their expected result | `make context` | a model change that alters an answer |

For a `stable: true` query the whole result must match; otherwise the columns must match and
the query must return rows (its numbers change as data arrives). When a result changes on
purpose, approve it again: the CSV diff in the pull request shows what changed.

## In the warehouse

`make context` loads every item into `context.items` in `data/warehouse/warehouse.duckdb`:

| Column | Holds |
| --- | --- |
| `id` | the item id, e.g. `glossary.preliminary_reading`, `column.dim_bill.is_passed` |
| `kind` | glossary, alias, rule, verified_query, table, column, metric |
| `title`, `text`, `text_he` | what retrieval searches and the agent reads |
| `source` | the YAML file, or `dbt` for generated items |
| `payload` | the whole item as JSON (for a verified query, with its compiled SQL) |

The agent's `get_context(question)` (milestone 2, in knesset-agent) searches this table.
