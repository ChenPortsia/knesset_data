-- J2: Which votes split the coalition most (most coalition MKs voting against), 25th Knesset?

WITH votes AS (
    SELECT *
    FROM {{ ref('fct_plenum_vote') }}
),

filtered AS (
    SELECT *
    FROM votes
    WHERE knesset_num = 25
      AND is_coalition_split
),

enhanced AS (
    SELECT
        vote_date,
        LEFT(vote_title, 70) AS vote_title,
        coalition_for,
        coalition_against,
        opposition_for,
        opposition_against,
        is_accepted
    FROM filtered
)

SELECT *
FROM enhanced
ORDER BY LEAST(coalition_for, coalition_against) DESC
LIMIT 10
