# Knesset Agent — Architecture

As of 2026-11-10

## Overview

Two projects with one contract between them: **knesset-data** builds a DuckDB warehouse, a search index and a context layer; **knesset-agent** is a LangGraph multi-agent system that reads all three and writes only to the context layer.

- **knesset-data** (data engineering): dlt ingests the Knesset OData v4 API and the ivrit-ai committee protocols into DuckDB, dbt models them into a star schema, and a Python batch adds chunks, embeddings, topics and sentiment.
- **knesset-agent** (AI engineering): a supervisor plans each question, routes steps to specialist subagents, lets them work as a team on shared state, verifies the answer, and learns from failures.

```
Sources:   Knesset OData v4          ivrit-ai committee protocols
                 \                          /
Project 1 (knesset-data):
   dlt ingest  ->  dbt transform  ->  NLP batch
       |               |                 |
 bronze + silver   gold (star schema)  rag (hybrid index)
                       |
                 Context layer  (catalog, glossary, metrics, verified queries, aliases, lessons)
                       |  agents read via tools              ^
Project 2 (knesset-agent):                                   | verified lessons
   Supervisor (LangGraph): understand, plan, execute, verify, answer, reflect
       |-- SQL Analyst | Live Data | Researcher | Statistician | Critic | Librarian --+
```

Data flows down from the sources into the warehouse and index; agents read everything through tools, and only the Librarian writes back, into the context layer, never into data.

**Design principles**

1. **Heavy work offline, agents thin.** NLP runs once in batch; agents query precomputed tables and indexes, so chat stays fast and cheap.
2. **The context layer is the contract.** Agents never read raw tables blind; they read documented models, a glossary, metrics and verified examples.
3. **Agents never write data, only knowledge.** The warehouse is read-only to agents; learned knowledge goes to a versioned, reviewable context store.
4. **Hybrid freshness.** The warehouse answers history and aggregates; a live OData tool covers what changed since the last sync.
5. **Every layer is measured.** Each milestone ships with its own eval, so the project has a definition of done.

## Project 1 — Data platform (knesset-data)

Two DuckDB files, so ingestion and transformation are separate processes that share only the bronze tables:

- `raw.duckdb` — written only by ingestion: `bronze` (every version of every source row) and `ops` (run records).
- `warehouse.duckdb` — written by dbt and the NLP batch, which read `raw.duckdb` read-only: `silver`, `gold`, `rag` and `context`. This is the file the agent reads.

### Sources

| Source | What it gives | Access |
| --- | --- | --- |
| Knesset OData v4 (`knesset.gov.il/OdataV4/ParliamentInfo/`) | Members, factions, bills, stages, votes per MK, laws, committee and plenum sessions, agenda items, parliamentary queries | Open REST, `@odata.nextLink` paging |
| ivrit-ai/knesset-committees (Hugging Face) | ~13K committee protocols, Nov 2018 – Jan 2026, with speaker labels and session metadata | Gated: accept terms; download text files only (repo is 827 GB, mostly audio) |
| Bill documents (`KNS_DocumentBill`) — v2 | Bill text and explanatory notes (.docx links) | File download + parse |

### Ingestion — dlt

- **OData pipeline:** one dlt resource per KNS table, loaded one table at a time so a failure stays contained. Pages by `Id` (keyset) because `@odata.nextLink` uses slow `$skip` paging; large tables are split into parallel `Id` ranges. Incremental on `LastUpdatedDate` with a 1-hour overlap, stored as SCD2 so bronze keeps every version of every row (e.g. bill status history). Checks after each load (reconciliation with the API's `$count`, volume, freshness) and a weekly check for rows deleted in the API; results go to `ops.ingestion_runs` / `ops.ingestion_tables` and a log file per run.
- **Protocols pipeline:** `snapshot_download` with `allow_patterns` for `raw.protocol.txt`, `speakers*.txt`, `metadata.json`, then a dlt Python resource that yields three tables: `sessions`, `speakers`, `speaker_segments`.
- Both land in `bronze` as-is. A schema contract fails a load if a column changes type; new columns are added and logged. `_dlt_load_id` links every row to its run.

### Transformation — dbt (dbt-duckdb)

- **SQL style:** uppercase SQL, every column cast explicitly, and every model as CTEs in the order `source → renamed → filtered → enhanced`. Model folders are numbered (`1_staging`, `2_intermediate`, `3_mart`) so they sort in build order.
- **staging:** one model per source table — English column names, types cast, Hebrew lookup codes decoded via seeds.
- **intermediate** (milestone 1): faction membership periods, votes with items and factions, faction-majority alignment, bills with stages (a hand-made status → stage seed), in-scope bill initiators, committee session ↔ bill bridge. Later:
  - `int_speaker_turns` — protocol text cut by speaker segment, one row per turn.
  - `int_speaker_link` — protocol speaker name → `person_id` (title stripping + fuzzy match against MKs serving that term); unmatched kept as `other`.
  - `int_session_bill_bridge` — committee session ↔ bill via `KNS_CmtSessionItem`.
- **marts (star schema):**

| Type | Models |
| --- | --- |
| Dimensions | `dim_person`, `dim_faction`, `dim_committee`, `dim_ministry`, `dim_knesset`, `dim_date`, `dim_bill` (with current stage and outcome), `dim_topic` (M6) |
| Facts | `fct_vote_result` (vote × MK, with faction, camp and faction-majority alignment), `fct_plenum_vote` (totals by camp), `fct_plenum_session`, `fct_committee_session`, `fct_committee_session_bill`, `fct_bill_initiator`, `fct_bill_reading`, `fct_faction_membership`, `fct_coalition_period` (derived from government posts + override seed), `fct_person_role` (committee chairs, ministers...), `fct_query` (with the asker's camp), `fct_agenda`; later `fct_bill_stage` (from bronze's version history) and `fct_turn` (text + topic + sentiment, M4/M6) |
| Aggregates | `agg_faction_pair_agreement_month` (voting blocs, by camp pair); later `agg_topic_month`, `agg_topic_faction_month`, `agg_person_topic_quarter` (min-count rule) |

- **tests:** unique / not-null keys, relationships between facts and dims, accepted values on decoded codes, a speaker-link match-rate threshold.
- **docs:** every model and column gets a Hebrew + English description. These feed the context layer directly.

### NLP batch (Python, between intermediate and marts)

1. **Chunking:** a speaker turn is the unit. Merge turns under ~40 tokens with their neighbours; split turns over ~400 tokens with ~15% overlap. Each chunk keeps session, committee, date, speaker and bill metadata.
2. **Contextual header:** prepend one line per chunk — `ועדת הכספים · 2024-11-12 · ח"כ X · דיון: …` — so the embedding carries where and who.
3. **Embeddings:** one pass with a Hebrew-capable model (multilingual-e5 or a retrieval-tuned NeoDictaBERT variant), stored in `rag.chunks`.
4. **Indexes:** DuckDB `vss` (HNSW) for dense search and `fts` (BM25) for keywords — one engine, hybrid search.
5. **Topics:** BERTopic on the same embeddings → topic per chunk, LLM-labelled once, then frozen into `dim_topic`.
6. **Sentiment:** Hebrew sentiment classifier per chunk → `fct_turn`.

The batch writes plain tables; dbt builds the gold aggregates on top, so the whole thing reruns with `dlt → dbt run → nlp → dbt run`.

### Context layer (schema `context`)

The context layer is what the agents read before they touch data. It has a **curated** part, kept in git as dbt seeds and YAML, and a **learned** part, written by agents into tables.

| Component | Content | Source |
| --- | --- | --- |
| Schema catalog | Every gold model and column with Hebrew + English descriptions, grain, joins | Exported from dbt `manifest.json` |
| Glossary | Parliamentary terms (קריאה טרומית, ועדה ראשית, סיעה, שאילתה ישירה) → definition + table/value mapping | Curated |
| Metrics | Named definitions as SQL: bill pass rate, vote alignment, committee attendance | Curated, as dbt semantic models or SQL snippets |
| Verified queries | Question → SQL → expected result, used as few-shot examples | Curated, grows from learning |
| Entity aliases | Nicknames and short names for MKs, committees, ministries, laws | Curated + learned |
| Topic catalog | Topic label, keywords, example chunks, synonyms | BERTopic output + curated labels |
| Learned notes | Lessons from past questions, with status, provenance and evidence | Agents (see Learning loop) |

All context items are embedded too, so `get_context(question)` returns only the few items relevant to each question instead of the whole catalog.

## Project 2 — AI system (knesset-agent)

A LangGraph supervisor graph: every question goes through understand → plan → execute (subagents) → verify → answer → reflect.

### Workflow nodes

1. **Understand:** resolve entities (MKs, committees, bills, topics, dates) against the context layer and score confidence. Unknown terms or low confidence → **Research** before planning; still ambiguous → ask the user one question.
2. **Plan:** break the question into steps, each with an owner subagent, inputs and expected output. Independent steps run in parallel.
3. **Execute:** subagents run their steps, reading and writing a shared **blackboard** in graph state (plan, findings, evidence, open questions).
4. **Verify:** the Critic checks every claim against evidence — numbers re-run, quotes matched to chunks, citations present. Fail → back to Plan with the critique (max 2 loops).
5. **Answer:** the Synthesizer writes the reply in the user's language, with citations and an optional chart.
6. **Reflect:** after the turn, record what failed or was unclear and propose context updates (see Learning loop).

### Subagents and tools

| Subagent | Job | Tools |
| --- | --- | --- |
| SQL Analyst | Structured questions over the warehouse | `get_context`, `run_sql` (read-only, row limit, timeout), `sample_values`, `explain_sql` |
| Live Data | Fresh facts newer than the last sync | `odata_query`, `list_entities`, `get_entity` |
| Researcher | What was said, by whom, when | `hybrid_search` (filters: committee, date, speaker, bill, topic), `rerank`, `get_session`, `expand_context` (neighbouring turns) |
| Statistician | Trends, comparisons, topic × sentiment over time | `query_aggregates`, `python_sandbox` (pandas on result sets), `make_chart` |
| Critic | Verifies claims before they reach the user | `run_sql`, `hybrid_search`, `check_citations` |
| Librarian | Owns the context layer: researches unknowns, proposes and validates updates | `search_context`, `sample_values`, `hybrid_search`, `propose_context`, `validate_context` |

Each subagent is its own small LangGraph (a ReAct loop with its own prompt and tools), compiled as a node in the supervisor graph. Tools are plain Python functions; keep each one narrow and typed.

### Team mode

For hybrid questions, subagents hand work to each other through the blackboard instead of through the supervisor.

*Example — "What did MKs say about the daycare bill in committee, and how did they vote?"*

1. Researcher finds the relevant committee turns and writes the bill IDs and speaker IDs it saw to the blackboard.
2. SQL Analyst picks up those IDs and returns each speaker's vote on the bill.
3. Statistician joins quotes with votes into a speaker table.
4. Critic checks that every quote and every vote is backed by a row or chunk.

The supervisor only decides when the team is done or stuck. A step budget (e.g. 12 tool calls) stops runaway loops.

### RAG pipeline

| Stage | Design |
| --- | --- |
| Chunking | Speaker turn as unit; merge short turns, split long ones with overlap (Project 1) |
| Indexing | Dense (DuckDB `vss`) + BM25 (`fts`), with metadata columns for filtering |
| Query rewrite | Rewrite into 2–3 Hebrew queries; add resolved entities as filters (committee, speaker, date range) |
| Retrieval | Hybrid search, top ~40, fused with reciprocal rank fusion |
| Reranking | Multilingual cross-encoder (e.g. bge-reranker-v2-m3) → top ~8 |
| Sorting | Relevance by default; chronological for "over time" questions; MMR for diversity across sessions and speakers |
| Expansion | Pull the neighbouring turns of each hit so a reply is read in context |
| Citation | Every quote carries session, committee, date and speaker |

### A2A

Start in-process: subagents as LangGraph nodes. Once the team works, expose the Researcher and SQL Analyst as **A2A servers** with agent cards, and have the supervisor call them through an A2A client. The blackboard contract stays the same, so this is a transport change, not a redesign.

### Memory

- **Short-term:** LangGraph checkpointer (SQLite) per conversation, so follow-ups like "and in the 24th Knesset?" work.
- **Long-term:** the context layer — shared by all users, not per-user.

## Learning loop

Agents learn by writing **proposed** knowledge to the context layer, and it only becomes trusted after a deterministic check or an eval run passes. Nothing they learn can change the data itself.

### 1. Check understanding (before answering)

The Understand node outputs an explicit interpretation, not just a plan:

- entities resolved, each with an ID and a confidence score
- glossary terms matched, and terms it did **not** recognise
- the assumptions it is making (e.g. "'this Knesset' = 25th")

Any unknown term or confidence below threshold triggers the Librarian.

### 2. Research (when it doesn't understand)

The Librarian tries, in order:

1. `search_context` — maybe it is known under another name.
2. `sample_values` — look in the data (`SELECT DISTINCT` on the likely column, fuzzy match).
3. `hybrid_search` — see how the term is used in protocols.
4. `list_entities` / OData metadata — check whether the API has something the warehouse lacks.
5. Still unclear → ask the user, and record the answer.

### 3. Reflect (after answering)

Triggers: the Critic failed an answer, the user gave a thumbs-down or a correction, or a clarification was needed. The Reflect node writes a **lesson** with:

| Field | Example |
| --- | --- |
| kind | alias · glossary term · verified query · join hint · topic synonym |
| content | "ועדת חוץ" → committee_id of ועדת החוץ והביטחון |
| evidence | the query or chunk that proved it |
| provenance | conversation ID, which agent, user-confirmed or not |
| status | proposed → verified → retired |

### 4. Promote safely

- **Auto-verify** only what a machine can check: an alias resolves to exactly one existing ID; a verified query runs and reproduces its stored result.
- **Eval-gated:** anything that changes prompts or few-shot examples is promoted only if the question bank does not regress.
- **Human review:** a weekly export of proposed lessons as a git diff to the curated seeds; you merge or reject.
- **Never learn from claims alone:** a user saying "X voted for Y" is checked against `fct_vote_result` before it becomes a lesson. This guards against poisoning.
- **Versioned and reversible:** each lesson has an ID and a `retired_at`, so a bad lesson can be switched off without a redeploy.

### 5. Measure that it learns

- Replay every failed question after its lesson is verified: it should now pass.
- Track clarification rate and first-try accuracy per week. If both don't improve, the loop isn't working.

*Scope note:* the learning loop is the most open-ended part. Ship it as aliases + verified queries first; prompt-level self-improvement is out of scope.

## Evaluation, observability and infra

The question bank is both the scope and the test suite: ~60 questions with known answers, run on every change.

### Evaluation

| What | How | Target to start |
| --- | --- | --- |
| Structured answers | Question bank, SQL ground truth, exact or numeric-tolerance match | 80% |
| Retrieval | RAGAS context precision / recall on ~30 labelled questions | baseline, then improve |
| Answer faithfulness | RAGAS faithfulness + Critic pass rate | 90% |
| Speaker linking | Match rate + 100 hand-checked links | >90% of MK turns |
| Topics / sentiment | ~200 hand-labelled chunks | report honestly |
| Learning | Failed questions replayed after their lesson is verified | pass after learning |

Question-bank categories: lookups, aggregates, votes, oversight, text-only, hybrid, trend, and ambiguous (the right answer is a clarifying question).

### Observability

- Langfuse (self-hosted, free) or LangSmith: a trace per question with every node, tool call, tokens and cost.
- Log the Understand node's interpretation and the Critic's verdict on every run — they are your best debugging signals.

### Infra

- Docker Compose, one container per task, each with its own dependencies and a small HTTP API to trigger and watch it: `ingestion` (dlt; `POST /runs`), `transformation` (dbt; `POST /builds`), later `nlp` (the NLP batch), plus `api` (FastAPI serving the LangGraph app) and `ui` (Chainlit). Airflow triggers the task services through their endpoints, in order.
- `warehouse.duckdb` is mounted read-only into `api`; the `context` schema is written through one small service function so agents can't write elsewhere.
- Scheduling: Airflow (see Pilot deployment, orchestration and observability).

### Repo layout

```
knesset_data/
  ingestion/        # dlt project: .dlt/config.toml, odata.py, protocols.py → bronze
  transformation/   # dbt project: models/1_staging, 2_intermediate, 3_mart; seeds/ (codes, glossary, aliases) → silver, gold
  nlp/              # chunk.py, embed.py, topics.py, sentiment.py → rag
  notebooks/        # discovery and profiling
  docs/             # questions the warehouse must answer
  tests/            # pytest unit tests
  Makefile          # ingest → dbt → nlp → dbt

knesset-agent/
  graph/            # supervisor.py, state.py (blackboard)
  agents/           # sql_analyst, live_data, researcher, statistician, critic, librarian
  tools/            # sql.py, odata.py, search.py, context.py, charts.py
  evals/            # question_bank.yaml, run_evals.py
  a2a/              # agent cards + servers (later milestone)
  ui/
```

## Pilot deployment, orchestration and observability

The pilot runs the full system, learning loop included, for a small invite-only group, with Airflow scheduling the pipelines and Langfuse tracing every agent step.

### Pilot stack

| Component | Choice | Why |
| --- | --- | --- |
| App | LangGraph + Chainlit on Cloud Run | Chainlit has auth, feedback buttons and step views built in |
| Access | Chainlit OAuth (Google/GitHub) or Cloud Run behind IAP | Invite-only; every message carries a `user_id` |
| Warehouse | DuckDB file from GCS, opened read-only | Many readers, no write risk |
| Writable store | Postgres (Neon or Supabase free tier) | Context layer, lessons, feedback, conversations; survives redeploys and handles concurrent writes |
| Traces | Langfuse (cloud free tier or self-hosted) | Full tree of nodes and tool calls per question |

The curated context lives in git and is loaded into Postgres on deploy; learned items are written to Postgres only.

### Orchestration — Airflow

Airflow runs separately from the app, locally with the Astro CLI while building and on a small GCP VM for the pilot (Cloud Composer costs too much for this). dbt runs through **astronomer-cosmos**, so each model is its own task.

| DAG | Schedule | Tasks |
| --- | --- | --- |
| `knesset_odata` | daily, night | dlt OData incremental → dbt staging/intermediate → dbt marts + tests → publish DuckDB to GCS → app reload |
| `knesset_protocols` | weekly | fetch new protocols → speaker turns → NLP batch on new chunks only → dbt marts → publish |
| `pilot_analytics` | daily | export Langfuse traces + feedback → dbt activity models → dashboard |
| `learning_review` | weekly | auto-verify proposed lessons → export the rest for human review |
| `eval_run` | nightly | run the question bank + replay failed questions → store scores over time |

### Data freshness

- **OData:** the Knesset publishes no refresh schedule. Its 2025 annual report describes OData as exposing the parliamentary activity in the Knesset's internal system that is shown on the website, and says the website updates continuously in real time. Whether OData is a live view or a periodic export is not documented; measure it with a freshness probe (below) and ask dataknesset@knesset.gov.il.
- **Mirrors pick their own cadence:** Open Knesset pulls daily; over.org.il refreshes about every 12 hours.
- **ivrit-ai protocols are a frozen snapshot** (sessions up to Jan 2026). Treat it as a one-time backfill. Newer protocols come from the OData committee-session document links, parsed with ivrit-ai's open-source extraction code.
- **Freshness probe:** an hourly Airflow task records `max(LastUpdatedDate)` per key table next to the fetch time. A few weeks of this shows the real update pattern and sets the DAG schedule.

### Observability

- **Langfuse callback** on every graph run, tagged with user, session and the subagents involved.
- **Scores on each trace:** user thumbs up/down, Critic verdict, Understand-node confidence.
- **Lesson ↔ trace link:** every proposed lesson stores its trace ID, so you can open the run that taught it.
- **LangGraph Studio** locally for stepping through the graph and inspecting blackboard state.
- **Chainlit Steps** in the UI: each node and tool call as a collapsible step, visible to admins or to everyone.

### Pilot success criteria

- First-try accuracy on repeated question types rises week over week.
- Clarification rate falls as aliases and glossary terms are learned.
- Replayed failed questions pass once their lessons are verified.
- Questions per active user and return rate, from `pilot_analytics`.

## Operational data store (everything logged to the DB)

Every run, step, log and action from every part of the system is written to one `ops` schema in Postgres, joinable through shared IDs. Langfuse stays as the trace viewer; Postgres is the system of record.

### Tables

| Area | Table | Written by | Grain |
| --- | --- | --- | --- |
| Orchestration | `pipeline_runs` | Airflow success / failure callbacks | one row per DAG run and task |
| Ingestion | `dlt_loads` | dlt `load_info`, persisted after each run | one row per load and table: rows, schema changes |
| Transformation | `dbt_runs`, `dbt_tests` | parsing `run_results.json` after each dbt run | one row per model / test result |
| NLP batch | `nlp_batches` | the batch script | chunks processed, model versions, topic and sentiment counts |
| Freshness | `freshness_probe` | hourly Airflow task | table, newest `LastUpdatedDate`, fetch time |
| App usage | `sessions`, `messages`, `user_events` | the Chainlit app | logins, questions, answers, clicks, feedback |
| Agent | `agent_runs`, `agent_steps` | a custom LangGraph callback (beside Langfuse) | one row per question / per node, subagent and tool call: input, output, tokens, cost, latency, error |
| Learning | `context_changes` | the Librarian and the review job | every lesson proposed, verified, rejected or retired: who, why, evidence |
| Evaluation | `eval_runs`, `eval_results` | the nightly eval DAG | one row per run / per question: expected, actual, pass |
| Errors | `app_errors` | a Python logging handler in every service | structured errors with stack trace |

### Shared IDs

- `run_id` ties a pipeline run across Airflow, dlt, dbt and NLP rows.
- `trace_id` ties an agent run across `agent_steps`, Langfuse, feedback and any lesson it produced.
- `session_id` and `user_id` tie everything a person did.
- `data_version` (the published DuckDB build) is stamped on every agent run, so an answer can be traced to the exact data it used.

### Using it

- A small dbt project over `ops` builds pipeline health, cost per question, agent routing, failure rates and learning metrics; the pilot dashboard reads only these models.
- **Privacy:** questions and answers are stored with the user's name. Tell pilot users up front, and set a retention period (e.g. 90 days for raw messages; aggregates kept).
- **Volume:** Postgres is enough for a pilot. Move `agent_steps` to a columnar store only if it grows large.

## Milestones

Eight milestones; each one ships something usable on its own, so you can stop after any of them with a finished project.

1. **Structured warehouse** — dlt OData pipeline, dbt star schema, tests, bilingual docs.
   - *Done when:* `dbt build` passes and you can answer 10 structured questions by hand in SQL.
2. **Context layer v1** — schema catalog export, glossary (~40 terms), aliases, 20 verified queries.
   - *Done when:* `get_context` returns the right items for every question in the bank.
3. **Single SQL agent + eval** — one LangGraph agent with SQL and live OData tools, question bank v1.
   - *Done when:* ≥ 80% on structured questions, with traces in Langfuse.
4. **Text layer** — protocols ingest, speaker turns, speaker linking, chunks, hybrid index.
   - *Done when:* > 90% MK link rate and a RAGAS baseline.
5. **Multi-agent team** — supervisor, Researcher, Statistician, Critic; blackboard and team mode.
   - *Done when:* hybrid questions pass and the Critic catches seeded wrong answers.
6. **Topics + sentiment** — BERTopic, sentiment, aggregates, trend charts.
   - *Done when:* the 200-chunk eval is reported, good or bad.
7. **Learning loop** — Understand → Librarian → Reflect, with aliases and verified queries only.
   - *Done when:* replayed failed questions pass after their lessons are verified.
8. **A2A + write-up** — Researcher and SQL Analyst as A2A servers; README with architecture, eval results, limitations.
   - *Done when:* published. **Then stop.**

**Out of scope:** fine-tuning models, plenum text, protocols before Nov 2018, stance detection, per-user memory, prompt-level self-modification.

**Fallbacks:** if sentiment is poor (M6), ship topic trends only. If the learning loop sprawls (M7), keep aliases only. The project is still complete.
