-- Q4: Committee sessions per month over the last 3 years

WITH committee_sessions AS (
    SELECT *
    FROM {{ ref('fct_committee_session') }}
),

dates AS (
    SELECT *
    FROM {{ ref('dim_date') }}
),

filtered AS (
    SELECT *
    FROM dates
    WHERE date_day >= DATE_TRUNC('month', CURRENT_DATE - INTERVAL 3 YEAR)
      AND date_day <= CURRENT_DATE
),

enhanced AS (
    -- Start from the calendar so months without sessions show 0
    SELECT
        filtered.year_month,
        COUNT(committee_sessions.committee_session_id) AS sessions
    FROM filtered
    LEFT JOIN committee_sessions
        ON filtered.date_day = committee_sessions.session_date
    GROUP BY filtered.year_month
)

SELECT *
FROM enhanced
ORDER BY year_month
