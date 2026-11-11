-- Q7: Which ministries received the most queries in the 24th Knesset, and how fast did they reply?

WITH queries AS (
    SELECT *
    FROM {{ ref('fct_query') }}
),

ministries AS (
    SELECT *
    FROM {{ ref('dim_ministry') }}
),

filtered AS (
    SELECT *
    FROM queries
    WHERE knesset_num = 24
),

enhanced AS (
    SELECT
        ministries.ministry_name,
        COUNT(*) AS queries,
        COUNT(*) FILTER (WHERE filtered.is_replied) AS replied,
        ROUND(AVG(filtered.reply_days), 0) AS average_reply_days,
        MEDIAN(filtered.reply_days) AS median_reply_days
    FROM filtered
    INNER JOIN ministries
        ON filtered.ministry_id = ministries.ministry_id
    GROUP BY ministries.ministry_name
)

SELECT *
FROM enhanced
ORDER BY queries DESC
LIMIT 10
