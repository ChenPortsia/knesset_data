-- J4: Which laws went from first reading to final approval fastest? (20th Knesset onward)

WITH bills AS (
    SELECT *
    FROM {{ ref('dim_bill') }}
),

filtered AS (
    SELECT *
    FROM bills
    WHERE is_passed
      AND days_first_to_final_reading IS NOT NULL
),

enhanced AS (
    SELECT
        knesset_num,
        LEFT(bill_name, 70) AS bill_name,
        origin,
        first_reading_date,
        final_reading_date,
        days_first_to_final_reading,
        committee_sessions
    FROM filtered
)

SELECT *
FROM enhanced
ORDER BY days_first_to_final_reading, committee_sessions
LIMIT 10
