-- J5: Is there a rush before the Knesset ends? Laws passed in each of a Knesset's last 6 months

WITH bills AS (
    SELECT *
    FROM {{ ref('dim_bill') }}
),

knessets AS (
    SELECT *
    FROM {{ ref('dim_knesset') }}
),

filtered AS (
    SELECT
        bills.knesset_num,
        bills.final_reading_date,
        knessets.finish_at
    FROM bills
    INNER JOIN knessets
        ON bills.knesset_num = knessets.knesset_num
    WHERE bills.is_passed
      AND bills.final_reading_date IS NOT NULL
      AND knessets.finish_at IS NOT NULL
),

enhanced AS (
    SELECT
        knesset_num,
        COUNT(*) FILTER (WHERE DATE_DIFF('month', final_reading_date, finish_at) BETWEEN 0 AND 0) AS last_month,
        COUNT(*) FILTER (WHERE DATE_DIFF('month', final_reading_date, finish_at) BETWEEN 1 AND 2) AS months_2_to_3,
        COUNT(*) FILTER (WHERE DATE_DIFF('month', final_reading_date, finish_at) BETWEEN 3 AND 5) AS months_4_to_6,
        COUNT(*) AS laws_in_term
    FROM filtered
    GROUP BY knesset_num
)

SELECT *
FROM enhanced
ORDER BY knesset_num
