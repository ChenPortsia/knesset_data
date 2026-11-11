# Milestone 2 plan: the context layer

**Goal.** Give the agent curated knowledge to read before it touches data: what each table
and column means, what parliamentary terms mean in this data, how named metrics are computed,
proven example queries, and what people call things.

**Done when** (from `ARCHITECTURE.md`): `get_context(question)` returns the right items for
every question in the question bank.

**Requirements** (from you): the context is version-controlled and easy to modify.

## What the research says

| Finding | Source | What we take from it |
| --- | --- | --- |
| Context *content* does most of the work: hard-task accuracy rose from 14–37% to 55–77%; retrieval scaffolding alone added 0–15 points. "Semantics first, scaffolding second, pre-computed macros only where an agent demonstrably fails." | [arXiv 2609.22259](https://arxiv.org/abs/2609.22259) | Spend the effort on writing good definitions, rules and examples; keep retrieval simple |
| A 4 KB hand-written document of measures, conventions and disambiguation rules added 17–23 points on three frontier models; model choice within a tier barely mattered | [arXiv 2604.25149](https://arxiv.org/abs/2604.25149) | Short, precise rules beat long dumps; write disambiguation rules explicitly |
| Within a semantic layer's scope, accuracy is 98–100% vs 84–90% for text-to-SQL; when the semantic layer can't answer, it says so instead of returning a plausible wrong number. Recommendation: both, for different things | [dbt Labs, 2026 benchmark](https://docs.getdbt.com/blog/semantic-layer-vs-text-to-sql-2026) | Named metrics (pass rate, loyalty, reply time) go through a deterministic semantic layer; exploration stays text-to-SQL with context |
| Verified queries (question + correct SQL, who verified it, when) are the most effective examples; 3–5 retrieved per question | [Snowflake verified query repository](https://docs.snowflake.com/user-guide/views-semantic/verified-query-repository), [practitioner report](https://dev.to/alexchen31337/from-68-to-100-how-we-built-a-text-to-sql-system-that-gets-smarter-every-day-19do) | Our 17 analyses become verified queries; retrieve a few per question |
| An open standard is forming: Apache Ossie (formerly Open Semantic Interchange), YAML with datasets, relationships, metrics and `ai_context` (instructions, synonyms, examples) on every level. Version 0.1.1, incubating | [Apache Ossie](https://github.com/open-semantic-interchange/OSI) | Use the same concepts and field names so we can export to it later; don't depend on it yet |
| Ready-made products: Wren AI (semantic layer + context in its own format), Cube (semantic layer server with MCP), Vanna (retrieval over DDL, docs and SQL pairs; main repo reportedly archived) | [comparison](https://querio.ai/articles/wren-ai-vs-vanna-ai-open-source-text-to-sql-compared) | Not adopted: each adds a server or product and its own format, for a context of a few hundred items |

## Decisions

1. **Git is the source of truth.** All curated context lives as YAML files in
   `knesset_data/context/`, reviewed in pull requests like code. The database copy is built
   from git and never edited by hand. (The learned context of milestone 7 will be proposed
   into the database and promoted into these files by review.)
2. **Generate what can be generated; write by hand only what can't.**
   - Schema catalog: generated from dbt's `manifest.json` (our English | Hebrew descriptions,
     grains, keys, relationship tests become joins). Never hand-edited.
   - Metrics: written once, in dbt's semantic layer (next to the marts), and exported into
     the context. One definition, used both to compute and to explain.
   - Glossary, aliases, rules and verified queries: hand-written YAML.
3. **Metrics through MetricFlow.** Named metrics are defined as dbt semantic models + metrics
   (open-source MetricFlow supports DuckDB). The agent can compute them deterministically
   instead of writing SQL. Questions outside the metrics stay text-to-SQL.
4. **Every item is checked in CI.** A context item that refers to a model, column, code or
   ID that doesn't exist fails the build; an alias must resolve to exactly one entity; every
   verified query must run and return its stored expected result. Bad context is caught
   before an agent reads it.
5. **One build command.** `make context` validates the YAML, builds the catalog, loads
   everything into the warehouse's `context` schema, and embeds it for retrieval.
6. **Simple retrieval.** Hybrid search (BM25 + embeddings with a Hebrew-capable model) over a
   few hundred items in DuckDB, as the architecture already plans for the protocols. No
   vector database, no extra server.
7. **Ossie-compatible concepts.** Field names follow Ossie where they overlap (`synonyms`,
   `instructions`, `examples`), so exporting to it later is a mapping, not a rewrite.

## Context item types

| Type | Written by | Example | Checked by |
| --- | --- | --- | --- |
| `table` / `column` | generated from dbt | `dim_bill.is_passed`: "True if passed third reading and became law" | dbt build |
| `metric` | dbt semantic layer | `bill_pass_rate` = passed bills / bills, by Knesset and origin | MetricFlow validation + a test query |
| `glossary` | hand | קריאה טרומית (preliminary reading) → `fct_bill_reading.reading = 'preliminary'` | referenced columns and values exist |
| `alias` | hand | "ועדת חוץ" → committee category of ועדת החוץ והביטחון | resolves to exactly one entity |
| `rule` | hand | "'This Knesset' means the current Knesset: `dim_knesset.is_current`"; "Use `fct_vote_result.camp`, never `dim_faction.was_in_coalition`, for coalition at a date" | referenced objects exist |
| `verified_query` | hand (from analyses) | Q1–Q10, J1–J7: question (Hebrew + English), SQL, expected result, verified by/at | runs and matches its stored result |

Example files:

```yaml
# context/glossary/legislation.yml
- id: glossary.preliminary_reading
  term_he: קריאה טרומית
  term_en: preliminary reading
  synonyms: [דיון מוקדם, טרומית]
  definition: >
    The first plenum vote on a private bill, before it goes to a committee.
    Government bills skip it.
  maps_to:
    - column: fct_bill_reading.reading
      value: preliminary
    - column: dim_bill.preliminary_reading_date

# context/aliases/committees.yml
- id: alias.committee.foreign_affairs_defense
  aliases: [ועדת חוץ, ועדת החוץ והביטחון, ועדת חוץ וביטחון, FADC]
  entity: committee_category        # resolves across Knessets
  key: {category_id: ...}

# context/verified_queries/legislation.yml
- id: vq.bills_by_origin
  question_he: כמה הצעות חוק הוגשו בכנסת ה-25 לפי סוג, וכמה עברו?
  question_en: How many bills were proposed in the 25th Knesset, by origin, and how many passed?
  sql_file: transformation/analyses/milestone_1/q01_bills_by_origin_25th_knesset.sql
  expected: context/expected/vq.bills_by_origin.csv
  verified_by: chen
  verified_at: 2026-11-11
```

## Repo layout

```
knesset_data/
  context/
    glossary/*.yml            # parliamentary terms, by area
    aliases/*.yml             # people, committees, factions, ministries, laws
    rules/*.yml               # disambiguation and usage rules
    verified_queries/*.yml    # question -> analysis SQL -> expected result
    expected/*.csv            # stored expected results
    schema/                   # JSON Schemas for each item type
    build.py                  # validate -> catalog -> load -> embed
  transformation/models/3_mart/_semantic_models.yml   # MetricFlow semantic models + metrics
knesset-agent/
  tools/context.py            # get_context(question) -> ranked items
  evals/question_bank.yaml    # questions + the context items each one needs
  evals/eval_context.py       # retrieval eval: does get_context return them?
```

## Steps

| # | Step | Done when |
| --- | --- | --- |
| 1 | **Item schemas and validation.** JSON Schemas per item type; `context/build.py validate` checks schema, unique ids, and that every referenced model, column, value and entity exists in the warehouse | a broken reference fails `make context` and CI |
| 2 | **Schema catalog** from `manifest.json`: tables and columns with English and Hebrew descriptions, grain, keys, joins (from relationship tests), contract types | every gold table and column is a context item |
| 3 | **Semantic layer.** MetricFlow semantic models for the main gold facts; ~10 metrics from the question bank: bill pass rate, faction loyalty, attendance, query reply time, committee sessions, coalition split rate... | `mf query` reproduces the matching analysis results |
| 4 | **Glossary** (~40 terms): readings, committee types, faction / list / alliance, coalition / opposition, query types, motion types, Knesset / assembly / sitting, no-confidence... each mapped to columns and values | all references valid; reviewed by you |
| 5 | **Aliases**: committees (by category, across Knessets), factions and parties (list names change every election), ministries, notable laws, frequent MK nicknames | each alias resolves to exactly one entity |
| 6 | **Rules** (~15): time ("this Knesset", "last year"), camps at a date, faction fallback (`faction_match`), scope (20th Knesset onward), known data gaps (25th-Knesset dates, missing votes) | referenced objects exist |
| 7 | **Verified queries** (≥ 20): the 17 analyses plus new ones to cover each theme, with Hebrew and English questions and stored expected results | CI runs each and compares with the stored result |
| 8 | **Load and embed**: `context.items` (one row per item: id, type, text, metadata), BM25 and embedding indexes in `warehouse.duckdb` | `make context` builds it in under a minute |
| 9 | **`get_context(question)`** in `knesset-agent/tools/context.py`: hybrid search, then type quotas (a few tables, glossary terms, rules, 3–5 verified queries) within a size budget | returns a small, ranked, typed list |
| 10 | **Question bank v1 + retrieval eval**: each question labelled with the item ids it needs; measure recall of those ids | **every question gets its required items** (the milestone's done-when) |
| 11 | **Docs**: `context/README.md`: how to add or change an item, how review and CI work | someone new can add a glossary term in 5 minutes |

Steps 1–2 come first: the validation and the generated catalog make every hand-written item
cheap to check. Steps 4–7 are mostly writing and can run in any order. Step 10's labels are
written as the items are.

## Risks and how we handle them

| Risk | Handling |
| --- | --- |
| Hand-written context drifts from the data | references validated against the warehouse in CI; verified queries re-run on every build |
| The context grows until retrieval returns noise | item types with quotas; the retrieval eval catches regressions |
| A wrong glossary entry or alias misleads the agent | every item reviewed in a PR; aliases must resolve uniquely; the agent cites item ids so a bad answer can be traced to its item |
| Hebrew search quality | Hebrew synonyms in items; hybrid search (exact Hebrew words via BM25, meaning via a multilingual model); measured by the retrieval eval |
| MetricFlow on DuckDB has gaps | metrics also exist as plain SQL in their verified queries; if MetricFlow fails a metric, the SQL is the fallback |
| Ossie changes | we only borrow its concepts; nothing depends on its tooling |

## Not in milestone 2

- The topic catalog (milestone 6) and learned notes (milestone 7).
- Postgres for the context store (the pilot); milestone 2 loads it into `warehouse.duckdb`.
- An MCP server: the agent calls `get_context` as a Python tool first (milestone 3);
  exposing it over MCP or A2A is a transport change later.
