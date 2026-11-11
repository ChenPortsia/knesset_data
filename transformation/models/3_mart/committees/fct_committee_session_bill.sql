-- Bills discussed in committee sessions | הצעות חוק שנדונו בישיבות ועדה
-- Grain: one row per committee session and bill

WITH session_bills AS (
    SELECT *
    FROM {{ ref('int_committee_sessions_bridged_to_bills') }}
),

enhanced AS (
    SELECT
        CAST(session_bill_id AS VARCHAR) AS session_bill_id,
        CAST(committee_session_id AS INTEGER) AS committee_session_id,
        CAST(bill_id AS INTEGER) AS bill_id,
        CAST(committee_id AS INTEGER) AS committee_id,
        CAST(knesset_num AS INTEGER) AS knesset_num,
        CAST(CAST(session_start_at AS DATE) AS DATE) AS session_date,
        CAST(agenda_items AS INTEGER) AS agenda_items
    FROM session_bills
)

SELECT *
FROM enhanced
