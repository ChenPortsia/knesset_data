# Questions the warehouse must answer

The agent's job: **analyse what the Knesset and its members do, find trends, and explain them.**
These questions set the scope of the data model. Each one names the tables it needs, so we only build what is used.
Later they become the agent's question bank (`knesset-agent/evals/question_bank.yaml`) with SQL ground truth.

The doc has three parts: the [themes](#themes) the model covers, the [milestone 1 questions](#milestone-1-ten-questions-to-answer-by-hand-in-sql)
that prove the warehouse works, and a [journalist's question bank](#a-journalists-question-bank): the questions a reporter
covering the Knesset would ask, each tagged with what it takes to answer.

## Themes

### 1. Legislation: what gets proposed, what passes
- How many bills were proposed per Knesset, by type (private, government, committee)? What share became law?
- Which topics or committees get the most bills? Which pass fastest?
- Who are the most active bill initiators, and how many of their bills passed?
- How long does a bill take from first reading to final approval?

*Needs:* `KNS_Bill`, `KNS_BillInitiator`, `KNS_Status`, `KNS_Committee`, `KNS_Person`

### 2. Votes: how members and factions vote
- How often does each MK vote with their faction? Who breaks ranks most?
- Which factions vote together most often (coalition/opposition patterns)?
- How did each MK vote on a specific bill or vote title?
- Attendance: what share of plenum votes did each MK take part in?

*Needs:* `KNS_PlenumVote`, `KNS_PlenumVoteResult`, `KNS_PersonToPosition` (MK → faction over time), `KNS_Faction`

### 3. Committees: where the work happens
- How many sessions did each committee hold per month? Is activity rising or falling?
- Which bills and topics did a committee discuss, and how often?
- Who chairs and sits on each committee?

*Needs:* `KNS_Committee`, `KNS_CommitteeSession`, `KNS_CmtSessionItem`, `KNS_PersonToPosition`

### 4. Oversight: how MKs question the government
- How many parliamentary queries does each ministry get, and how fast does it answer?
- Which MKs submit the most queries and motions for the agenda?

*Needs:* `KNS_Query`, `KNS_Agenda`, `KNS_GovMinistry`, `KNS_Person`

### 5. People and careers
- Who served in which Knesset, faction, ministry and committee role?
- Which MKs switched factions?
- Gender balance per Knesset and per role.

*Needs:* `KNS_Person`, `KNS_PersonToPosition`, `KNS_Position`, `KNS_Faction`, `KNS_KnessetDates`

### 6. Trends over time
- Activity per month: bills, votes, committee sessions, queries. Before and after elections or wars?
- What changes between the 20th and the 25th Knesset?

*Needs:* all facts + `dim_date`

### 7. What was said (milestone 4+, protocols)
- What did MKs say about topic X in committee, and how did they vote on it?
- How does the tone of a debate change over time?

*Needs:* protocols, chunks, topics, sentiment (not in milestone 1)

## Milestone 1: ten questions to answer by hand in SQL

The "done when" check for the structured warehouse. Each must be answerable from `gold` only.
**Answered:** the SQL is in `transformation/analyses/milestone_1/`; `make answers` runs it
against `warehouse.duckdb` with the raw database not attached, so it proves gold is enough.

| # | Question | Main models |
| --- | --- | --- |
| 1 | How many bills were proposed in the 25th Knesset, by type, and how many passed? | `dim_bill` |
| 2 | Top 10 MKs by private bills initiated in the 24th Knesset, with how many passed | `fct_bill_initiator`, `dim_bill`, `dim_person` |
| 3 | Which committee held the most sessions in 2024? | `fct_committee_session`, `dim_committee` |
| 4 | Monthly committee sessions over the last 3 years | `fct_committee_session`, `dim_date` |
| 5 | How did each faction vote on a given vote? | `fct_vote_result`, `fct_plenum_vote`, `dim_faction` |
| 6 | Each MK's rate of voting with their faction's majority in the 25th Knesset | `fct_vote_result` (`voted_with_faction`), `dim_person` |
| 7 | Which ministry received the most queries in the 24th Knesset, and its average reply time? | `fct_query`, `dim_ministry` |
| 8 | Which MKs changed faction during a Knesset? | `fct_faction_membership`, `dim_faction`, `dim_person` |
| 9 | Share of women MKs in each Knesset since the 20th | `fct_faction_membership`, `dim_person` |
| 10 | Which bills were discussed most often in committee sessions? | `dim_bill` (`committee_sessions`), `fct_committee_session_bill` |

## A journalist's question bank

The questions a parliamentary reporter would bring to this data: who works, who doesn't, who
breaks ranks, what gets rushed through, and what the government avoids answering. Each is tagged
with what it takes to answer, which makes the list a roadmap for the next models.

| Tag | Meaning |
| --- | --- |
| ✅ | Answerable now from gold |
| 🧩 | The data is loaded; needs a new model or seed |
| 📥 | In the Knesset API, not loaded yet (add a table to ingestion) |
| 🗣 | Needs the committee protocols (milestone 4) or topics and sentiment (milestone 6) |
| ⛔ | Needs a source outside the Knesset |

### Legislation and productivity
- ✅ Which MKs propose the most private bills, and what share of them ever pass? Who proposes many and passes none?
- ✅ What share of government bills passed in each Knesset? Did the current government pass more or less of its agenda than the last one?
- ✅ Which bills passed with the most committee sessions behind them, and which passed with almost no committee discussion?
- ✅ How long does a bill take from first reading to final approval, and which laws were rushed through in days? (`dim_bill.days_first_to_final_reading`; analysis J4)
- ✅ Which laws passed in the last weeks before the Knesset dissolved? Is there a pre-election rush? (analysis J5: 38 laws in the 25th Knesset's last month)
- 🧩 How many bills are "copy-paste": the same title proposed again by different MKs or in a new Knesset? (needs fuzzy matching of bill names)
- 📥 Which existing laws were amended most often in this Knesset? (`KNS_IsraelLawBinding`, `KNS_LawBinding`)
- 📥 Which government bills were split or merged on the way, and with what? (`KNS_BillSplit`, `KNS_BillUnion`)
- 🗣 What topics do private bills cover compared with government bills?

### Votes, loyalty and rebellions
- ✅ Which MKs vote against their own faction most often? On which votes did they rebel?
- ✅ How did each faction vote on a given bill or vote? Was any faction split?
- ✅ Which votes were decided by the smallest margin? Who was absent from them?
- ✅ Which MKs miss the most plenum votes? Does attendance drop near elections?
- ✅ Which opposition factions vote with the coalition most often, and on what? (`agg_faction_pair_agreement_month`, camp at the time; analysis J6)
- ✅ Which pairs of factions vote alike most often? Has that changed since the last election? (`agg_faction_pair_agreement_month`)
- ✅ How did MKs who later switched factions vote in the months before they switched? (`fct_faction_membership` + `fct_vote_result`)
- 🗣 Do MKs who speak against a bill in committee still vote for it in the plenum?

### Government oversight
- ✅ Which ministries take longest to answer parliamentary queries, and which leave the most unanswered?
- ✅ Which MKs ask the most queries, and of which ministries?
- ✅ Do opposition MKs ask more queries than coalition MKs? (`fct_query.asker_camp`; analysis J7: about 80% come from the opposition in every Knesset)
- ✅ Has the share of answered queries risen or fallen from Knesset to Knesset?
- ✅ How many motions for the agenda does each MK propose, and how many does the government accept?
- ✅ Which ministers answered their queries least often? (`fct_query` joined to `fct_person_role` ministers by ministry and date)
- ✅ How many no-confidence votes did each government face, and what was the closest one? (`fct_plenum_vote.is_no_confidence`; governments by date from `fct_person_role`)
- 📥 What do the query and motion documents actually say? (`KNS_DocumentQuerie`, `KNS_DocumentAgenda`)

### Committees: where the power is
- ✅ Which committees meet most and least? Which meet behind closed doors most often?
- ✅ Which committees handle the most bills, and how many of those bills pass?
- ✅ How has committee activity changed month by month, around wars, recesses and elections?
- ✅ Who chairs each committee, and how long has each chair held the post? (`fct_person_role`; analysis J3)
- ✅ Which committees are run by coalition chairs and which by opposition chairs? (`fct_person_role` + `fct_coalition_period`)
- 🗣 Which MKs speak most in committee, and which never speak? Which members actually attend? (attendance lists are in the protocols)
- 🗣 How much of a committee session is spent on the bill on the agenda versus other topics?

### MK profiles and accountability
- ✅ For any MK: bills initiated and passed, votes attended, loyalty to the faction, queries asked, motions proposed.
- ✅ Which MKs who entered from the 20th Knesset on are most active? (careers before the 20th need a lower `from_knesset`)
- ✅ Which MKs changed faction during a Knesset, and when?
- ✅ Which MKs were also ministers or deputy ministers, and does their parliamentary activity drop while in government? (`fct_person_role`)
- ✅ How did each MK's activity change after their party joined or left the coalition? (`fct_vote_result.camp`, `fct_coalition_period`)
- 📥 Which lobbyists are registered, and which clients do they represent? (`V_Lobbyists`, `V_LobbyistsClients`)
- ⛔ How do MKs' parliamentary records compare with their public statements, assets or expenses? (outside sources)

### Coalition dynamics and political crises
- ✅ Which votes split the coalition? On which did coalition MKs vote with the opposition? (`fct_plenum_vote.is_coalition_split`; analyses J1, J2)
- ✅ How stable was each government: parties joining and leaving, no-confidence votes, failed coalition votes? (`fct_coalition_period`, `fct_plenum_vote`)
- ✅ What legislation passed under the Bennett–Lapid government compared with Netanyahu's 2022 government? (`dim_bill.final_reading_date` + government periods)
- ✅ Which bills were voted down with coalition MKs voting against? (`fct_plenum_vote`: `is_accepted`, `coalition_against`)
- ⛔ How did public polls move around key votes? (outside source)

### Timing and the calendar
- ✅ How many votes take place after midnight, and on what kinds of bills? (4,204 of 19,663 votes since 2015 were held between midnight and 6am; 655 carry a date only, shown as exactly 00:00, so leave those out)
- ✅ How does activity differ between the winter and summer sittings and the recesses?
- ✅ Did plenum and committee activity change during the war that began in October 2023?
- ✅ Which bills were passed in long "voting marathons", with dozens of votes in one night? (`fct_plenum_session.votes`, `fct_plenum_vote.voted_at`)

### What was said (protocols and topics)
- 🗣 What did MKs say about a given bill in committee, and did their vote match?
- 🗣 Which topics dominate committee discussion, and how has that shifted since the war?
- 🗣 Which government officials appear before committees most often, and for which ministries?
- 🗣 How does the tone of debate on a topic change over a Knesset? Which topics are most polarised?
- 🗣 Which MKs speak most about a given topic (cost of living, security, religion and state)?

### Comparisons across Knessets
- ✅ How do the 20th to 25th Knessets compare on bills proposed and passed, votes held, committee sessions and queries?
- ✅ How has the share of women MKs changed, and are women MKs as active by these measures?
- ✅ Are short Knessets (the 21st and 22nd lasted months) productive at all, per month of their term? (`dim_knesset` dates + `dim_bill`)
- 📥 How does today's Knesset compare with the 1990s? (lower `from_knesset` in the ingestion config; vote results start in 2003)

### How the coalition is known
No Knesset table says which factions are in the coalition. `fct_coalition_period` derives it:
a faction is in the coalition while one of its MKs holds a government post. Three known
exceptions are corrected in `transformation/seeds/coalition_overrides.csv`, each with its reason:
Ra'am (in the Bennett–Lapid coalition without ministries), Yamina (in opposition while one MK
joined the government) and Shas (left the government in July 2025 but stayed in the coalition,
voting with Likud on 99.7% of votes). When a result looks wrong, check whether a party supported
the government without posts, or held posts without supporting it, and add a row with its reason.

### Answered so far
`transformation/analyses/journalist/` answers seven of these questions (J1–J7); run them with
`uv run python transformation/scripts/run_analyses.py --folder journalist`.

### What to build next
1. **The protocols** (milestone 4): everything tagged 🗣.
2. **Bill similarity**: the remaining 🧩, "copy-paste" bills proposed again and again.
3. **API tables not loaded yet** (📥): law amendments, bill splits and merges, lobbyists, and the text of queries and motions.
