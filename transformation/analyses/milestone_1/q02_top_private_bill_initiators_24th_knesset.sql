-- Q2: Top 10 MKs by private bills initiated in the 24th Knesset, with how many passed

WITH bill_initiators AS (
    SELECT *
    FROM {{ ref('fct_bill_initiator') }}
),

bills AS (
    SELECT *
    FROM {{ ref('dim_bill') }}
),

persons AS (
    SELECT *
    FROM {{ ref('dim_person') }}
),

filtered AS (
    SELECT
        bill_initiators.person_id,
        bills.is_passed
    FROM bill_initiators
    INNER JOIN bills
        ON bill_initiators.bill_id = bills.bill_id
    WHERE bills.knesset_num = 24
      AND bills.origin = 'private'
      AND bill_initiators.is_initiator
),

enhanced AS (
    SELECT
        persons.full_name,
        COUNT(*) AS private_bills_initiated,
        COUNT(*) FILTER (WHERE filtered.is_passed) AS passed
    FROM filtered
    INNER JOIN persons
        ON filtered.person_id = persons.person_id
    GROUP BY persons.full_name
)

SELECT *
FROM enhanced
ORDER BY private_bills_initiated DESC, passed DESC
LIMIT 10
