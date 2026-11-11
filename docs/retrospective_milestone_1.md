# Retrospective: milestone 1 and the start of milestone 2

A walk through what we built, in the order a data engineer would do it: what was decided and
why, what broke and how it was fixed, what is still uncertain, and what to take away.
Each section ends with a short exercise, so you can redo the important parts yourself.

## 1. The path we took

| Step | What | Why this order |
| --- | --- | --- |
| 1 | Scaffold two repos: `knesset_data` (data platform) and `knesset-agent` (agents) | The agents only read data; keeping them apart keeps that boundary real |
| 2 | Look at the API by hand: tables, sizes, keys, dates, paging speed | You can't design a pipeline for a source you haven't seen |
| 3 | Decide the scope: 20th Knesset (2015) onward, useful tables only | Load what answers questions, not everything that exists |
| 4 | Sample loads (2 pages per table) before the full load | Find bugs in minutes, not after an hour |
| 5 | Discovery notebook: profile every table | Write down what the data really looks like before modelling it |
| 6 | Questions doc | Models are built to answer questions; without questions you model everything |
| 7 | Ingestion as its own process, with checks, logs and run tables | Ingestion must be able to fail, retry and report without dbt |
| 8 | Full load on your Mac (~53 min), then daily incremental (~2 min) | |
| 9 | dbt staging → intermediate → gold, with tests and contracts | Each layer has one job |
| 10 | Answer the milestone 1 questions as dbt analyses | Proof that the model works, and a regression test later |
| 11 | Docker service per task, with HTTP endpoints | The same command runs on your Mac, in CI, and later in Airflow |
| 12 | Context layer + MetricFlow (milestone 2 start) | The agent needs meaning, not only tables |

## 2. The discovery process

This is how to start any API batch pipeline. These are the questions we answered, in order,
and what we found.

**1. What is there?** Read `$metadata` (the OData schema): table names, columns, types, keys.
→ About 40 `KNS_*` tables. Each has an `Id` key and almost all have `LastUpdatedDate`.

**2. How big is it?** `$count` per table.
→ A few huge tables (vote results: millions of rows, MK-per-vote), many small ones (factions,
committees, statuses). This decides everything about speed.

**3. How do you page?** Try the API's own `@odata.nextLink`, time deep pages.
→ It uses `$skip`: page 1 is fast, page 5,000 is very slow (the server counts from the
start every time). Paging by key (`Id gt <last> ORDER BY Id`) is constant speed.
Max 100 rows per page.

**4. How do you get only what changed?** Look for a reliable "updated at" column.
→ `LastUpdatedDate`. We load rows updated since the last run, minus one hour of overlap
(`lag`), because clocks and in-flight writes can miss rows exactly at the boundary.

**5. How does it fail?** Send requests in parallel and watch.
→ The site's firewall answers bursts with HTTP 473/481 (not standard), and some date-filtered
`$count`s time out and return 200 with an empty body after 30 seconds.

**6. Can you trust it?** Profile: nulls, duplicates, ranges, codes, orphans.
→ Duplicate rows with the same `Id`, `-1` meaning "none", votes with no time, results whose
vote is missing, and a day when the source rewrote thousands of dates. (Details in section 4.)

**7. What do people need from it?** Write the questions down.
→ `docs/questions.md`: the milestone 1 questions, then a journalist's question bank. Every
gold model exists because a question needs it.

**Exercise:** pick one table you haven't looked at (e.g. `KNS_DocumentBill`) and answer the
seven questions in the notebook yourself.

## 3. Decisions

### Ingestion

| Decision | Why | What we gave up |
| --- | --- | --- |
| **dlt** for loading | Handles schema, state, merges and retries; we only write "how to fetch a page" | One more tool to learn; some magic (e.g. it dropped all-null columns until we gave it column hints) |
| **Keyset paging** (`Id gt`) | Constant speed on any table size | Must check pages arrive in order; we do (`clean_page`) |
| **Parallel ranges** (8 workers, 20,000 ids each) | Full load in ~1 hour instead of many | Harder code (threads), and it triggers the firewall, so we needed retries |
| **Scope from the 20th Knesset** (`from_knesset = 20`) | Enough history for trends, a fraction of the size; one setting to widen it | No history before 2015 for now |
| **Incremental on `LastUpdatedDate`, with 1 h lag** | Daily run takes ~2 minutes | Trusts the source to update that column; we check that (row counts vs API) |
| **SCD2 in bronze** (`_dlt_valid_from/_to`) | Keeps every version of every row, so we can see what the source changed and when | Bigger bronze; every query needs "current rows only" (the `is_current` macro) |
| **Detect deletes weekly** (compare all ids) | Incremental loads can't see deleted rows | Deletes show up up to a week late |
| **Checks warn, don't fail** (except a failed table) | The source is noisy; a failing pipeline every day teaches you to ignore it | You must read the warnings (they're in `ops.ingestion_tables` and the log) |
| **Two DuckDB files** (raw / warehouse) | DuckDB allows one writer per file: ingestion writes raw, dbt writes warehouse, and dbt reads raw read-only | Two files to move around |
| **Everything in `config.toml`** | Change scope, workers, retries without changing code | |

### Transformation

| Decision | Why |
| --- | --- |
| **Three layers**: staging (rename, cast, clean), intermediate (join, derive), gold (star schema) | Each problem is fixed once, in one place. A source quirk is fixed in staging and never seen again |
| **Generated staging models** (`make staging-models`) | 20 near-identical models; a generator keeps them consistent and is easy to rerun when the source changes |
| **SQL style**: UPPERCASE, explicit casts, CTEs `source → renamed → filtered → enhanced` | Every model reads the same way; explicit casts mean a source type change breaks loudly in staging |
| **Gold = tables with enforced contracts** | Column names and types are a promise to the agent; a change must be deliberate |
| **Seeds for knowledge the source lacks** (status stages, role kinds, coalition overrides) | Human knowledge in git, with a reason per row, reviewed like code |
| **Derived facts instead of trusting one column** (coalition from government roles) | The source has no "coalition" table; we derive it and correct known exceptions in a seed |
| **Test severity**: errors for our logic, warnings for source gaps | Known source gaps shouldn't block the build; our own mistakes should |
| **Analyses for the questions** | Each answer is SQL in git; later the same files become verified queries |

### Platform and context

| Decision | Why |
| --- | --- |
| **A Docker service per task with HTTP endpoints** | Airflow (later) only needs to call `POST /run`; each task is isolated |
| **CI**: lint, tests, `dbt parse`, `context check`, Docker builds | Mistakes are caught before merge, without data |
| **Context as YAML in git, checked by code** | Easy to edit, reviewed in PRs, history for free; the database copy is rebuilt, never edited |
| **MetricFlow** for metrics | A metric is defined once; the agent asks for "bill pass rate by Knesset" instead of writing a ratio itself (where LLMs make mistakes) |
| **Verified queries with expected CSVs** | A known-good answer is also a test: if a model change alters it, the check fails |

## 4. Issues and errors

Grouped by where the problem came from. "Lesson" is the general rule to keep.

### The source

| Issue | How it happened | Fix | Lesson |
| --- | --- | --- | --- |
| Deep pages very slow | `nextLink` uses `$skip`; the server rescans from the start | Keyset paging by `Id` | Never page large tables by offset |
| HTTP 473/481 | The site's firewall throttles bursts with non-standard codes | Retry 429, 470–499 and 5xx with exponential backoff | Retry what is temporary, learn the source's own codes from the logs |
| Same `Id` returned 2–3 times (vote 37161 ×3, 23 copies) | Source bug: identical duplicate rows | `clean_page` drops identical repeats, logs differing ones, fails on missing or out-of-order ids | Validate pages, don't assume the key is unique |
| `JSONDecodeError` on vote tables (on your Mac) | Date-filtered `$count` takes >30 s; the server gives up and returns 200 with an empty body | `EmptyResponse` error; the count check becomes a warning | A 200 is not proof of success; check the body |
| `-1` in committee and type codes | The source uses `-1` for "none" | `NULLIF(..., -1)` in the staging generator | Find sentinel values in profiling, fix them in staging |
| Thousands of 25th-Knesset dates rewritten on 2026-11-04 | The source re-saved position and membership records | SCD2 kept the old versions; noted in the quirks table | Keep history: it shows you what changed in the source |
| 655 votes have a date but no time | Old records | Kept as dates; a rule tells the agent | Document it; don't invent a time |
| 95 vote results with no vote (2 votes missing) | Missing in the source | Relationship test as a warning | Orphans from the source are warnings, not errors |
| All-null columns missing from bronze | dlt doesn't create a column it has never seen a value for | Column hints from `$metadata` | The schema should come from the source's schema, not from the data |

### Our code

| Issue | How it happened | Fix | Lesson |
| --- | --- | --- | --- |
| **Deadlock** when one range failed | Other threads waited forever to put pages into a full queue nobody read | `put()` returns False once `stop` is set; regression test with a timeout | Every thread needs a way to stop; test the failure path, not only the happy one |
| Volume check skipped the wrong run | It skipped the newest run instead of the first full load | `QUALIFY ROW_NUMBER() > 1` | Test checks with small fake data |
| Incremental state lost after a refactor (cloud copy) | Turning resources into a dlt source changed the state key | Full refetch | State is tied to names; renaming a source or resource resets it |
| 25th-Knesset factions missing from government 35 | Role periods merged across Knessets | Partition by `knesset_num` | When collapsing periods, partition by everything that defines "the same thing" |
| J6 answer was wrong | Used `dim_faction.was_in_coalition` (ever) instead of the camp at the time of the vote | Camp per vote, `camp_pair` | "Ever" vs "at the time" is the most common modelling bug in time-based data |
| Shas labelled opposition after July 2025 | Its ministers resigned but it still voted with the coalition | Override row in `coalition_overrides.csv` with a reason | Derived facts need a reviewed exception list |
| J7 used only the Knesset fallback | Didn't try the dated membership first | Dated membership first, then the Knesset | Use the most precise source first, fall back explicitly, and record which one was used (`faction_match`) |
| Seed error after adding a column | dbt tried to insert into the existing seed table | `+full_refresh: true` for seeds | Seeds are small; always rebuild them |
| MetricFlow errors | No time spine; ratio built from measures; wrong group-by name | Time spine on `dim_date`; ratios from metrics; `vote__knesset_num` | Read the error, then the docs; new tools have their own rules |
| Context tests failed | Catalog code assumed every field exists; paths outside the repo | `.get()`, a `relative()` helper | Test with minimal fake inputs, not only the real manifest |

### Environment and process

| Issue | How it happened | Fix | Lesson |
| --- | --- | --- | --- |
| Repo name `knesset-data` not found | It's `knesset_data` | Renamed the folder | Check names, don't assume |
| 403 from knesset.gov.il in the cloud | The cloud environment blocked the host | Environment network settings | Sandboxes have network rules; read the error source (proxy vs site) |
| Broken `.venv` after renaming the folder | venv scripts store absolute paths | Recreate `.venv` | Virtual envs aren't movable |
| Full load killed after 30 min (cloud) | Background command time limit | Rerun with a longer limit | Know your runner's limits before a long job |
| Docker builds failed in the cloud | Docker Hub rate limit and the proxy | CI builds the images instead | Have a second place where things run |
| Your Mac had older code | Later PRs weren't merged yet | New PR, then `git pull` | Before debugging, check you're running the same version |
| `dbt` not found by the API outside Docker | It ran a bare `dbt` from `PATH` | Use the `dbt` next to the running Python | Don't rely on `PATH` in services |

## 5. What I'm not sure about

Be skeptical of these. Each one is a place to check or decide.

1. **Coalition membership is derived, not given.** We infer it from ministers per government,
   plus three overrides (Ra'am, Yamina, Shas). Factions with no minister, MKs who left a party
   or partial support are judgment calls. Every coalition/opposition number depends on this.
2. **Party aliases across Knessets.** Joint lists and splits (e.g. Blue and White, Yamina,
   the Joint List) make "the same party" fuzzy. Which faction ids belong to each alias is my
   judgment and needs your review.
3. **Faction loyalty and coalition split are our definitions.** "Majority of the faction" and
   "coalition MKs voted both ways" are reasonable but not official. They're written down as
   metric descriptions so they can be argued with.
4. **Glossary definitions** were written by me from general knowledge of Knesset procedure,
   not checked against the Knesset's rules of procedure.
5. **Postgres vs DuckDB.** `ARCHITECTURE.md` says Postgres for ops and context. We kept them
   in DuckDB (simpler, one tool). When the agent runs as a service with several users, the
   context and ops logs probably belong in Postgres. Decide before milestone 3.
6. **SCD2 on the biggest tables.** It keeps every version, which is great for history but
   makes bronze grow. Fine at our scope; worth checking once a year of daily loads exists.
7. **Docker on your Mac** was never run end to end by me (CI builds the images and checks
   `/health`). `make up` on your Mac is worth one try.
8. **MetricFlow** is a heavy dependency for 20 metrics. It earned its place by matching the
   analyses exactly, but if it becomes a burden, the metric definitions are simple enough to
   keep as plain SQL.
9. **Verified queries are mostly `stable: false`**: only the column names and "has rows" are
   checked, because their numbers change as data arrives. They'd catch a broken query, not a
   subtly wrong one.

## 6. What we learned

1. **Look before you build.** An hour of discovery found the slow paging, the duplicates and
   the `-1` codes before they became production bugs.
2. **Start small, then scale.** Sample loads (2 pages per table) found most bugs in minutes.
3. **The source is never clean.** Plan for duplicates, sentinels, silent rewrites, missing
   rows and "successful" empty responses. Validate, log, and keep history.
4. **Separate the steps.** Ingestion, transformation and context each run, fail and get
   checked on their own. A broken model never stops the daily load.
5. **Fix each problem once, at the lowest layer.** A quirk fixed in staging disappears from
   every model above it.
6. **Time is the hard part.** Most modelling bugs were "ever" vs "at the time": coalition,
   faction, role periods. Always ask "as of when?"
7. **Write human knowledge down, with a reason.** Seeds, overrides, glossary and rules are
   knowledge that isn't in the data; in git they're reviewed and have history.
8. **Warnings are signals, not noise.** Known gaps are warnings; your logic failing is an
   error. Then a new warning means something.
9. **Answers are tests.** The milestone 1 analyses became verified queries; a change that
   breaks an answer now fails a check.
10. **Test the failure path.** The deadlock only happened when something else failed.

## 7. Exercises to make it your own

1. **Trace one row.** Pick a bill on the Knesset website and follow it:
   `bronze.kns_bill` → `stg_odata__bill` → `int_bills_joined_to_stages` → `dim_bill`.
   At each step, write down what changed and why.
2. **Read one day's run.** Open `logs/ingestion/<run_id>.log` and query
   `ops.ingestion_tables` for the same run. Explain each warning.
3. **Break something on purpose.** Change a staging cast to the wrong type, or a glossary
   column to a wrong name, and run `make dbt` / `make context-check`. See which check catches
   it.
4. **Add a question end to end.** Pick a journalist question, write the analysis, check it by
   hand, add it as a verified query, `make context-approve`.
5. **Widen the scope.** Set `from_knesset = 19` in a sample run and see what changes.
6. **Argue with a definition.** Pick `faction_loyalty_rate` or the Shas override and decide
   whether you agree. If not, change it and see which answers move.
