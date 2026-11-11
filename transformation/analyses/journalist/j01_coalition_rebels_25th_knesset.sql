-- J1: Which coalition MKs voted against their own faction most often in the 25th Knesset?

WITH vote_results AS (
    SELECT *
    FROM {{ ref('fct_vote_result') }}
),

persons AS (
    SELECT *
    FROM {{ ref('dim_person') }}
),

filtered AS (
    SELECT *
    FROM vote_results
    WHERE knesset_num = 25
      AND camp = 'coalition'
      AND voted_with_faction IS NOT NULL
),

enhanced AS (
    SELECT
        persons.full_name,
        persons.latest_faction_name,
        COUNT(*) FILTER (WHERE NOT filtered.voted_with_faction) AS votes_against_faction,
        COUNT(*) AS comparable_votes
    FROM filtered
    INNER JOIN persons
        ON filtered.person_id = persons.person_id
    GROUP BY persons.full_name, persons.latest_faction_name
)

SELECT *
FROM enhanced
ORDER BY votes_against_faction DESC
LIMIT 10
