-- J7: Do opposition MKs ask more parliamentary queries than coalition MKs?

WITH queries AS (
    SELECT *
    FROM {{ ref('fct_query') }}
),

enhanced AS (
    SELECT
        knesset_num,
        COUNT(*) FILTER (WHERE asker_camp = 'opposition') AS by_opposition,
        COUNT(*) FILTER (WHERE asker_camp = 'coalition') AS by_coalition,
        COUNT(*) FILTER (WHERE asker_camp IS NULL) AS camp_unknown,
        ROUND(100.0 * COUNT(*) FILTER (WHERE asker_camp = 'opposition') / COUNT(*), 1) AS opposition_percent
    FROM queries
    GROUP BY knesset_num
)

SELECT *
FROM enhanced
ORDER BY knesset_num
