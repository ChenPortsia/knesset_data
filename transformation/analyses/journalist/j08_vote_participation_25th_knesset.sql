-- J8: Which MKs took part in the smallest share of plenum votes in the 25th Knesset?
-- Only MKs who voted have a row in fct_vote_result, so the share is counted against the
-- votes held between an MK's first and last vote in that Knesset (their time serving).

WITH vote_results AS (
    SELECT *
    FROM {{ ref('fct_vote_result') }}
),

plenum_votes AS (
    SELECT *
    FROM {{ ref('fct_plenum_vote') }}
),

persons AS (
    SELECT *
    FROM {{ ref('dim_person') }}
),

served AS (
    SELECT
        person_id,
        knesset_num,
        MIN(vote_date) AS first_vote_date,
        MAX(vote_date) AS last_vote_date,
        COUNT(*) FILTER (WHERE took_part) AS votes_taken_part
    FROM vote_results
    WHERE knesset_num = 25
    GROUP BY person_id, knesset_num
),

compared AS (
    SELECT
        served.person_id,
        served.votes_taken_part,
        COUNT(*) AS votes_held
    FROM served
    INNER JOIN plenum_votes
        ON served.knesset_num = plenum_votes.knesset_num
        AND plenum_votes.vote_date BETWEEN served.first_vote_date AND served.last_vote_date
    GROUP BY served.person_id, served.votes_taken_part
),

enhanced AS (
    SELECT
        persons.full_name,
        persons.latest_faction_name,
        compared.votes_held,
        compared.votes_taken_part,
        ROUND(100.0 * compared.votes_taken_part / compared.votes_held, 1) AS participation_percent
    FROM compared
    INNER JOIN persons
        ON compared.person_id = persons.person_id
    WHERE compared.votes_held >= 500
)

SELECT *
FROM enhanced
ORDER BY participation_percent, full_name
LIMIT 15
