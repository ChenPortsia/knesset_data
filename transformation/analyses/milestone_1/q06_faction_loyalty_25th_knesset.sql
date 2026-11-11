-- Q6: Each MK's rate of voting with their faction's majority in the 25th Knesset
-- (MKs with at least 100 comparable votes; lowest first = most independent)

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
      AND voted_with_faction IS NOT NULL
),

enhanced AS (
    SELECT
        persons.full_name,
        persons.latest_faction_name,
        COUNT(*) AS comparable_votes,
        ROUND(100.0 * COUNT(*) FILTER (WHERE filtered.voted_with_faction) / COUNT(*), 1) AS with_faction_percent
    FROM filtered
    INNER JOIN persons
        ON filtered.person_id = persons.person_id
    GROUP BY persons.full_name, persons.latest_faction_name
    HAVING COUNT(*) >= 100
)

SELECT *
FROM enhanced
ORDER BY with_faction_percent
LIMIT 15
