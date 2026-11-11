-- Q3: Which committee held the most sessions in 2024?

WITH committee_sessions AS (
    SELECT *
    FROM {{ ref('fct_committee_session') }}
),

committees AS (
    SELECT *
    FROM {{ ref('dim_committee') }}
),

filtered AS (
    SELECT *
    FROM committee_sessions
    WHERE YEAR(session_date) = 2024
),

enhanced AS (
    SELECT
        committees.committee_name,
        COUNT(*) AS sessions
    FROM filtered
    INNER JOIN committees
        ON filtered.committee_id = committees.committee_id
    GROUP BY committees.committee_name
)

SELECT *
FROM enhanced
ORDER BY sessions DESC
LIMIT 5
