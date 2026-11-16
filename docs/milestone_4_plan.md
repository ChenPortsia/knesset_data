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

On the Mac (M1 Max, processor only): `e5-large` 0.8 chunks a second (168 hours for 500,000),
`potion` 4,182 a second (2 minutes).

The large model is out of reach on a plain processor. Whether the fast one searches well
enough is what the search test (step 9) will show; keyword search carries part of the load
either way.

### What the search test showed (step 9)

On the pilot, with the fast model: keyword search finds the right passage for most Hebrew
questions, and `potion`'s meaning search for few (6 of 27). On a reduced set, `e5-large`
with keywords found all 27, including English questions and rephrasings that share no words
with the passage. So the fast model is not good enough on its own, and the large one is too
slow to build on a plain processor. Step 10 has to find a strong model at a workable cost:
the Mac's GPU, a rented GPU for a few hours, an embedding API, or a mid-sized model.
The tables are in knesset-agent's README.

### The decision (step 10)

Measured on the Mac (M1 Max), 100 chunks:

| How `e5-large` runs | Chunks a second | The pilot | 500,000 chunks | Same vectors as the processor |
| --- | --- | --- | --- | --- |
| Processor | 1.1 | 2.5 hours | 123 hours | |
| GPU, through PyTorch (`e5-large-torch`) | 14.2 | 12 minutes | 9.8 hours | 1.000 |
| GPU, through CoreML | ran out of memory and was killed | | | |

**Use `e5-large` on the Mac's GPU through PyTorch.** It is 13 times faster than the
processor, its vectors are identical, and the full load fits in one night. The run saves
every 256 chunks, so it can be stopped and continued. The agent keeps embedding questions on
the processor (one question takes a fraction of a second), which is safe because the
vectors are the same.

Order: first re-embed the pilot with it (12 minutes) and rerun the text test, to see the
gain on the whole pilot and not only on the reduced set. Then the full load.

**Result on the pilot** (10,271 chunks embedded on the Mac in 12 minutes): the right passage
is in the top 6 for 24 of 27 questions (17 of 26 with the fast model), answers are correct
for 21 of 27 (19 of 26) and faithful for 25 of 27 (23 of 26). That is the milestone's
baseline, and the go-ahead for the full load.

Expect for all 11,144 sessions: about 35 minutes to download, about 10 hours to embed,
and a published database of roughly 5 GB (2 GB of vectors, the rest text). Search compares
a question with every vector; if that gets slow at 500,000 chunks, a vector index is the
next step.

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

## The chunk is where knowledge about the text lives

Each chunk row carries what search can filter on, beside its text and vector. Adding a
column doesn't change a chunk's text, so it needs no re-embedding.

| On every chunk | State |
| --- | --- |
| Session, committee, Knesset, date | done |
| Its place in the session (`position`), so the chunks before and after can be read | done |
| Speakers as written, and the people they link to | done |
| People and bills mentioned in the text | later |
| Topic | milestone 6 |
| Sentiment | milestone 6 |

## Where the text comes from

Only from the Hugging Face dataset. The Knesset's OData API gives each session's facts
(committee, date, agenda items) and links to its protocol as a Word document; it has no
protocol text. So the sessions the dataset lacks (9% to 21% per Knesset, and everything
after January 2026) have no text yet. Filling them means downloading those documents
through the links and cutting them into speakers ourselves: planned, not built.

## What the other sources turned out to be (looked at 2026-11-16)

| Source | Finding |
| --- | --- |
| `ivrit-ai/knesset-plenums` | 1,551 plenum sessions, 53 million words (984 sessions and 34 million words since 2015). The text is the full "דברי הכנסת", but **without speaker names**: the speeches follow each other as bare paragraphs, and only the table of contents lists who spoke. Its session ids are not ours; every session date since 2015 matches one of our plenum session dates |
| `ivrit-ai/VoxKnesset` | 66,670 short plenum segments, each tied to a speaker: a sample for voice research, not the record. Gated separately |
| The Knesset's protocol documents (`KNS_DocumentCommitteeSession`: 201,813 rows; `KNS_DocumentPlenumSession`: 21,928) | Keyed by our own session ids, and current (protocols of June 2026 are there). A committee protocol is a real `.docx` in which each speaker is a short paragraph of its own style ending with a colon, and the attendance list gives every guest's role and organisation. Readable with Python's standard library |
| `KNS_DocumentBill` (111,663 rows) | Bill texts at each stage, background material, the law as published |
| `KNS_DocumentAgenda` (23,021), `KNS_DocumentSecondaryLaw` (7,630) | Motion texts and committee conclusions; regulations |
| `KNS_DocumentQuerie`, `V_Lobbyists`, `V_LobbyistsClients` | Listed by the API but answer "not found" |

So the Knesset's own documents are the better road for the plenum (they should carry the
speakers, which ivrit's plenum text does not) and the only road for what ivrit lacks.
`make peek-documents` looks inside one committee and one plenum document to confirm it.

## Decision: one text source, the Knesset's own documents (2026-11-16)

`make peek-documents` looked at a committee protocol and a plenum protocol from each Knesset,
20 to 25. All twelve are real `.docx` files with the same paragraph styles:

| Style | Marker (from the 21st Knesset) | Means |
| --- | --- | --- |
| `af6` | `<< יור >>` | the chair speaks |
| `a4` | `<< דובר >>` | an MK or minister starts speaking |
| `-` | `<< דובר_המשך >>` | the same speaker continues after an interruption |
| `af9` | `<< אורח >>` | a guest speaks (committees) |
| `af5` | `<< קריאה >>` | a call from the floor, usually with the caller's name |
| `a6` | `<< נושא >>`, `<< הצח >>` | the subject or bill now under discussion |
| `af1`, `--`, `af2` | | a vote: its number, the counts, the outcome |
| none | | what is said |

So one parser that reads the styles covers every year and both kinds of session. Compared
with the ivrit datasets, the documents also give the kind of speaker, the subject each
speech belongs to, the votes inside the debate, guests' roles, plenum speakers (ivrit's
plenum text has none), every session (ivrit has 83%), and anything new.

**The ivrit datasets are dropped as a source.** The full load from ivrit is cancelled: its
embeddings would have to be redone once the text came from the documents. The ivrit pilot
stays as the reference the new parser is compared against, then its pipeline is removed.

New steps, replacing 11 and 12:

| # | Step | Done when |
| --- | --- | --- |
| A | Load the document link tables with the OData pipeline (`KNS_DocumentCommitteeSession`, `KNS_DocumentPlenumSession`) | they are in bronze, incremental like the rest |
| B | **Documents pipeline**: download each session's protocol file once, store its paragraphs with their styles in bronze | the pilot sessions load; a second run downloads nothing |
| C | **Turns from styles** in dbt, for committees: speaker, kind, subject, text. Compare with ivrit's turns on the pilot | the same sessions give the same speakers and text, or the differences are understood |
| D | Speaker linking, `fct_turn`, chunks and search on the new turns; rerun the text test | no worse than the ivrit pilot |
| E | **Plenum** through the same pipeline, with votes linked by their number in the session | plenum speeches are searchable next to the votes |
| F | Full load, one night of embedding | everything from 2015 on is searchable |

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
| 6 | **Chunking** with the context line | done: 12,397 chunks from the 254 sessions, 188 words on average, 260 at most. A chunk under 40 words joins a neighbour (257 such chunks became 1); tests show no word or turn is lost |
| 7 | **Embedding the slice, timed** on your Mac, with two models | built (`make embed-benchmark`); timed in the cloud session, see below; the Mac's numbers are still needed |
| 8 | **Indexes and `search_protocols`**, published | done: `make publish` carries the chunks, vectors and keyword index; the agent answered a trial question from the passages. A proper measure is step 9 |
| 9 | **Text question bank and RAGAS baseline** on the slice | built: 27 questions and `make eval-text` in knesset-agent; search baseline recorded there. The answer scores come from a full run with a model |
| 10 | **Decide the full load** from steps 7 and 9: which model, where it runs, how long | decided: see "The decision" below |
| 11 | **Full load**, then rerun steps 4 and 9 on everything | next: one overnight run on the Mac |
| 12 | **Plenum protocols**: from the Knesset's own documents if `make peek-documents` shows they carry speakers (ivrit's plenum text has none); link speeches to plenum sessions and votes, add test questions | plenum speeches are searchable next to the votes |
| 13 | **Mentions on chunks**: people and bills named in the text, matched against our own tables (no model, no hand tagging) | a chunk can be filtered by who and what it mentions |
| 14 | **Docs**: both READMEs, `ARCHITECTURE.md`, the context (new tables, terms, rules) | someone new can load a slice and search it |

After this milestone: session summaries and a reranker (each kept only if the text test
improves), then the Knesset-documents pipeline for missing and new protocols and bill texts.
`make odata-survey` profiles the API tables we don't load, to choose what to add.

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
