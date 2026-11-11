-- Initiators of bills in scope (20th Knesset onward) | יוזמי הצעות חוק מהכנסת ה-20 ואילך
-- Grain: one row per bill and person
-- Bill initiators load for all Knessets (the API has no Knesset column on them);
-- this keeps only those of bills in scope.

WITH bill_initiators AS (
    SELECT *
    FROM {{ ref('stg_odata__bill_initiator') }}
),

bills AS (
    SELECT *
    FROM {{ ref('stg_odata__bill') }}
),

filtered AS (
    SELECT
        bill_initiators.*,
        bills.knesset_num
    FROM bill_initiators
    INNER JOIN bills
        ON bill_initiators.bill_id = bills.bill_id
),

enhanced AS (
    SELECT
        CAST(bill_initiator_id AS INTEGER) AS bill_initiator_id,
        CAST(bill_id AS INTEGER) AS bill_id,
        CAST(person_id AS INTEGER) AS person_id,
        CAST(knesset_num AS INTEGER) AS knesset_num,
        CAST(is_initiator AS BOOLEAN) AS is_initiator,
        CAST(ordinal AS INTEGER) AS ordinal,
        CAST(is_initiator AND ordinal = 1 AS BOOLEAN) AS is_first_initiator
    FROM filtered
)

SELECT *
FROM enhanced
