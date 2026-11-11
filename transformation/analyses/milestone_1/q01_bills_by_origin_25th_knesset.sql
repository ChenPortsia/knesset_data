-- Q1: How many bills were proposed in the 25th Knesset, by origin, and how many passed?

WITH bills AS (
    SELECT *
    FROM {{ ref('dim_bill') }}
),

filtered AS (
    SELECT *
    FROM bills
    WHERE knesset_num = 25
),

enhanced AS (
    SELECT
        origin,
        COUNT(*) AS bills,
        COUNT(*) FILTER (WHERE is_passed) AS passed,
        ROUND(100.0 * COUNT(*) FILTER (WHERE is_passed) / COUNT(*), 1) AS pass_rate_percent
    FROM filtered
    GROUP BY origin
)

SELECT *
FROM enhanced
ORDER BY bills DESC
