-- Who initiated or joined each bill | מי יזם או הצטרף לכל הצעת חוק
-- Grain: one row per bill and person

WITH bill_initiators AS (
    SELECT *
    FROM {{ ref('int_bill_initiators_filtered') }}
),

enhanced AS (
    SELECT
        CAST(bill_initiator_id AS INTEGER) AS bill_initiator_id,
        CAST(bill_id AS INTEGER) AS bill_id,
        CAST(person_id AS INTEGER) AS person_id,
        CAST(knesset_num AS INTEGER) AS knesset_num,
        CAST(is_initiator AS BOOLEAN) AS is_initiator,
        CAST(is_first_initiator AS BOOLEAN) AS is_first_initiator,
        CAST(ordinal AS INTEGER) AS ordinal
    FROM bill_initiators
)

SELECT *
FROM enhanced
