# Questions the warehouse must answer

The agent's job: **analyse what the Knesset and its members do, find trends, and explain them.**
These questions set the scope of the data model. Each one names the tables it needs, so we only build what is used.
Later they become the agent's question bank (`knesset-agent/evals/question_bank.yaml`) with SQL ground truth.

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
