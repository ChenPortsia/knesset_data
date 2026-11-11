-- Q10: Which bills were discussed in the most committee sessions?

WITH bills AS (
    SELECT *
    FROM {{ ref('dim_bill') }}
),

enhanced AS (
    SELECT
        bill_name,
        knesset_num,
        committee_name,
        committee_sessions,
        stage
    FROM bills
)

SELECT *
FROM enhanced
ORDER BY committee_sessions DESC
LIMIT 10
