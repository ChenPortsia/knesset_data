-- J6: Which coalition and opposition factions voted alike most often in the 25th Knesset?
-- (camps at the time of each vote; pairs with at least 200 shared votes)

WITH agreement AS (
    SELECT *
    FROM {{ ref('agg_faction_pair_agreement_month') }}
),

filtered AS (
    SELECT *
    FROM agreement
    WHERE knesset_num = 25
      AND camp_pair = 'coalition-opposition'
),

enhanced AS (
    SELECT
        faction_a_name,
        faction_b_name,
        SUM(votes) AS votes,
        ROUND(100.0 * SUM(agreed) / SUM(votes), 1) AS agreement_percent
    FROM filtered
    GROUP BY faction_a_name, faction_b_name
    HAVING SUM(votes) >= 200
)

SELECT *
FROM enhanced
ORDER BY agreement_percent DESC
LIMIT 10
