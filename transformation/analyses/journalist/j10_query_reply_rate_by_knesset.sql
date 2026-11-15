-- J10: Has the share of answered parliamentary queries changed from Knesset to Knesset?

WITH queries AS (
    SELECT *
    FROM {{ ref('fct_query') }}
),

enhanced AS (
    SELECT
        knesset_num,
        COUNT(*) AS queries,
        COUNT(*) FILTER (WHERE is_replied) AS replied,
        ROUND(100.0 * COUNT(*) FILTER (WHERE is_replied) / COUNT(*), 1) AS replied_percent,
        ROUND(AVG(reply_days), 1) AS average_reply_days
    FROM queries
    GROUP BY knesset_num
)

SELECT *
FROM enhanced
ORDER BY knesset_num
