# Milestone 4 plan: the text layer

**Goal.** Make what was said in committee searchable: load the committee protocols, cut them
into speaker turns, link each speaker to a person, chunk and embed the text, and give the
agent a search tool over it.

**Done when** (from `ARCHITECTURE.md`): more than 90% of MK turns are linked to the right
person, and there is a RAGAS baseline (a measured starting score for search-and-answer).

**Not the goal.** Topics and sentiment (milestone 6), the multi-agent team (5), plenum text,
protocols before November 2018.

## What discovery found

Looked at the source before planning (no protocol text read yet: the files need a login).

| Question | Finding |
| --- | --- |
| Where is the text? | `ivrit-ai/knesset-committees` on Hugging Face: one folder per committee session |
| How does it join our data? | The folder name **is** `committee_session_id`. Folder `2073683` is the session of 2018-11-06 in `fct_committee_session` |
| What is in a folder? | 14 files. We need four small text files: `raw.protocol.txt` (about 80 KB), `speakers.txt`, `speakers.segments.txt`, `metadata.json`. The rest is audio and alignment data (one session's audio is 90 MB) |
| How big? | The repo is 692 GB. The four text files are about 0.2 MB per session: 2 to 3 GB for all sessions |
| Coverage | About 13,000 sessions, November 2018 to January 2026. We have 14,500 sessions held since November 2018, so some are missing, and anything after January 2026 is not there |
| Access | Gated: you accept the licence on the dataset page and use a personal access token. The licence is ivrit.ai's own: read it before we load anything |
| The text itself | Protocols are edited minutes, not word-for-word transcripts. Speaker names are kept in separate files, which is what makes speaker turns possible |

## What the real files look like

Loaded and profiled the pilot slice (the Finance Committee in 2024, 214 sessions) plus 40
other sessions.

| Finding | What it means |
| --- | --- |
| The dataset has 11,144 sessions and 101.6 million words; all but one are in our `fct_committee_session` | the join is clean |
| It covers 79% to 91% of the sessions held in each Knesset (45% in the short 21st) | report coverage; don't claim "every session" |
| `raw.protocol.txt` is the speech only; the header with the agenda and the attendance list is in another file | attendance is possible later, from `raw.full.protocol.txt` |
| Segments are character positions into the text and cover 100% of it | a turn is `text[start:end]`, nothing is lost |
| Turns are short: half are under 43 characters, 75% under 100 | merging neighbours matters more than splitting |
| MKs are marked in the name: `ינון אזולאי (ש"ס)`, `היו"ר משה גפני` | "is this an MK" comes from the protocol itself |
| 98.8% of MK-marked speakers match a person serving in that Knesset by exact name | the 90% target looks reachable with simple rules; the rest are spelling (`יחימוביץ` / `יחימוביץ'`), middle names, and a few broken names |
| Low speaker ids (below 10,000,000) usually repeat across sessions, but not reliably (14% carry more than one name), and they are not our `person_id` | link by name only. Carrying a link by id was tried and linked different people, so it was removed |
| "Speakers" include `קריאה` (an interjection from the floor) and section headings | keep them as their own kind, not as people |
| `metadata.json` is 125 KB of audio alignment scores; `manifest.csv` has the fields we need | we download three files per session, not four |
| A few files are broken: 9 segments point to a speaker that isn't listed | reported as a warning by the pipeline |
| Speed: 214 sessions in 35 seconds | all 11,144 in about half an hour |

## The main risk: embedding time

**Revised after profiling:** 101.6 million words is about 400,000 to 500,000 chunks, not the
1.2 million first guessed from file sizes. The rest of this section still holds, with the
times roughly halved.

Rough size: 13,000 sessions × about 27,000 tokens ≈ 350 million tokens ≈ 1.2 million chunks.

| Option | Speed (to be measured) | 1.2M chunks |
| --- | --- | --- |
| Large model on CPU (what the context uses) | a few chunks a second | more than a week: not workable |
| Large model on the Mac's GPU | maybe 100+ a second | a few hours |
| Small model on CPU | 5 to 10 times the large one | a day or two |
| An embedding API | fast | costs money per token, and sends the text out |

So the plan starts with a **pilot on one slice** (one committee, one year: about 250 sessions)
that builds every step end to end and **measures** speed and search quality. The full load
is sized from those numbers, not from guesses. The embeddings also need room: 1.2M vectors
is about 5 GB with the large model, 2 GB with a small one.

### Measured (cloud session, 4 processor cores, no GPU)

| Model | Vector size | Chunks a second | The pilot (12,725 chunks) | 500,000 chunks |
| --- | --- | --- | --- | --- |
| `e5-large` (the context layer's model) | 1,024 | 0.6 | 5.7 hours | 222 hours |
| `potion` (a static model, no neural network at run time) | 256 | 2,147 | 6 seconds | 4 minutes |

The large model is out of reach on a plain processor. Whether the fast one searches well
enough is what the search test (step 9) will show; keyword search carries part of the load
either way.

## Decisions

1. **A second, separate ingestion pipeline** (`ingestion/protocols.py`, dlt), like OData:
   own command, own checks, own log. It downloads only three text files per session
   (never audio) and loads four bronze tables: `protocol_manifest`, `protocol_text`,
   `protocol_speakers`, `protocol_segments`.
2. **Load only sessions we know.** A protocol is loaded when its id is in
   `fct_committee_session`; the rest are counted and reported.
3. **Incremental by folder.** A session's protocol never changes, so each run loads only
   folders not loaded yet. The first run can stop and resume.
4. **dbt does the structure, Python does the language.** dbt: staging, speaker turns,
   speaker linking, the facts. Python (`nlp/`): chunking, embedding, indexes. Python writes
   plain tables; dbt builds on them.
5. **Speaker linking is rules first, measured.** Strip titles (ח"כ, השר, היו"ר, ד"ר...),
   then match the name to people who held a role in that Knesset: exact, then close match.
   The committee's chair that day resolves "היו"ר". Everyone else (officials, guests) stays
   `other` with the name as written. A hand-checked sample of 100 links gives the accuracy.
6. **A turn is the unit; a chunk is what is searched.** Short turns are merged with their
   neighbours, long ones split with overlap. Every chunk carries its session, committee,
   date, speaker and bills, and starts with one line saying where and who, so the embedding
   knows the setting.
7. **One engine for search.** DuckDB keyword search (BM25) plus vector search, merged the
   same way as the context search. Filters (committee, dates, speaker, bill) are plain SQL.
8. **The published database gets the text.** `make publish` adds `rag.chunks` and its
   indexes, so the agent's file stays the only thing it opens.
9. **The agent gets one new tool, `search_protocols`,** and a rule for when to use it.
   Questions about what was said stop being out of scope. The full Researcher agent is
   milestone 5.
10. **Evaluation in two parts.** Linking: match rate, plus the 100 hand-checked links.
    Search and answer: about 30 questions with the session and passage that answer them;
    RAGAS scores context precision, context recall and faithfulness. Run on a cheap model,
    a few questions at a time, like the answer test.

## Layout after this milestone

```
knesset_data/
  ingestion/protocols.py                  # Hugging Face → bronze.protocol_*
  transformation/models/1_staging/protocols/
  transformation/models/2_intermediate/protocols/
      int_speaker_turns.sql               # one row per turn: who, text, order
      int_speaker_links.sql               # speaker name → person_id, with how it matched
  transformation/models/3_mart/protocols/
      fct_turn.sql                        # turns with person, faction, camp, session
  nlp/chunk.py, nlp/embed.py, nlp/index.py   # → rag.chunks, keyword + vector indexes
knesset-agent/
  tools/search.py                         # search_protocols(query, filters)
  evals/text_bank.yaml, evals/eval_text.py   # RAGAS baseline
```

## Steps

| # | Step | Done when |
| --- | --- | --- |
| 1 | **Access and a look at real files**: accept the licence, token, profile real sessions (formats, sizes, speaker name shapes, oddities) | done: see "What the real files look like" |
| 2 | **Protocols pipeline** for the pilot slice: bronze tables, checks (sessions found vs expected, empty texts), run log | done: 214 sessions in 35 seconds; a second run loads nothing |
| 3 | **Staging and speaker turns** in dbt | done: 91,667 turns from 254 sessions |
| 4 | **Speaker linking** and its measurement | done on the pilot: 99.4% of MK-marked speakers linked (99.8% of MK turns); a dbt test fails below 90%. The few non-exact links were read by hand; a 100-link check waits for the full load |
| 5 | **`fct_turn`** with person, faction and camp; a first analysis (who spoke most) | done; bills per turn left for later |
| 6 | **Chunking** with the context line | done: 12,725 chunks from the 254 sessions, 183 words on average, 253 at most; tests show no word is lost |
| 7 | **Embedding the slice, timed** on your Mac, with two models | built (`make embed-benchmark`); timed in the cloud session, see below; the Mac's numbers are still needed |
| 8 | **Indexes and `search_protocols`**, published | a query returns the right passages for 10 trial questions |
| 9 | **Text question bank and RAGAS baseline** on the slice | the scores are recorded, good or bad |
| 10 | **Decide the full load** from steps 7 and 9: which model, where it runs, how long | a written decision |
| 11 | **Full load**, then rerun steps 4 and 9 on everything | more than 90% of MK turns linked; baseline on the full data |
| 12 | **Docs**: both READMEs, `ARCHITECTURE.md`, the context (new tables, terms, rules) | someone new can load a slice and search it |

## Risks and how we handle them

| Risk | Handling |
| --- | --- |
| Embedding takes too long or too much room | the pilot measures it; step 10 decides before anything big runs |
| The licence doesn't allow our use | read it in step 1, before loading; the fallback is the Knesset's own protocol documents |
| Speaker names are messy (titles, spelling, two people with one name) | match only within people serving in that Knesset; keep how each link was made; measure by hand |
| Protocols are edited minutes, not exact speech | say so in the context; quote passages, don't claim exact words |
| Sessions missing from the dataset, and nothing after January 2026 | report coverage per committee and year; newer protocols come later from the Knesset's document links |
| The published file gets large | measure in the pilot; if needed the text goes in a second published file |
| Test cost | cheap model, few questions at a time, cached prompts |

## What I need from you

1. **Open the dataset page and read the licence**: `https://huggingface.co/datasets/ivrit-ai/knesset-committees`. If you're comfortable with it, accept the terms there.
2. **A Hugging Face access token** (read access is enough). On your Mac it goes in `.env` as `HF_TOKEN`. For this cloud session I'd ask for it through the secure form.
3. **Which slice for the pilot?** My suggestion: the Finance Committee in 2024, about 250 sessions.
