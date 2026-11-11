-- Which bills each committee session discussed | אילו הצעות חוק נדונו בכל ישיבת ועדה
-- Grain: one row per committee session and bill
-- Committee agenda items load for all Knessets; sessions in scope keep it to the 20th onward.

WITH committee_session_items AS (
    SELECT *
    FROM {{ ref('stg_odata__committee_session_item') }}
),

committee_sessions AS (
    SELECT *
    FROM {{ ref('stg_odata__committee_session') }}
),

filtered AS (
    SELECT *
    FROM committee_session_items
    WHERE item_type_id = 2  -- bill
),

items_per_session_and_bill AS (
    -- A bill can be on one session's agenda more than once: one row per session and bill
    SELECT
        committee_session_id,
        item_id AS bill_id,
        COUNT(*) AS agenda_items,
        MIN(ordinal) AS first_ordinal
    FROM filtered
    GROUP BY committee_session_id, item_id
),

enhanced AS (
    SELECT
        CAST(MD5(CONCAT_WS('|', items_per_session_and_bill.committee_session_id, items_per_session_and_bill.bill_id)) AS VARCHAR) AS session_bill_id,
        CAST(items_per_session_and_bill.committee_session_id AS INTEGER) AS committee_session_id,
        CAST(items_per_session_and_bill.bill_id AS INTEGER) AS bill_id,
        CAST(committee_sessions.committee_id AS INTEGER) AS committee_id,
        CAST(committee_sessions.knesset_num AS INTEGER) AS knesset_num,
        CAST(committee_sessions.start_at AS TIMESTAMP) AS session_start_at,
        CAST(items_per_session_and_bill.agenda_items AS INTEGER) AS agenda_items,
        CAST(items_per_session_and_bill.first_ordinal AS INTEGER) AS first_ordinal
    FROM items_per_session_and_bill
    INNER JOIN committee_sessions
        ON items_per_session_and_bill.committee_session_id = committee_sessions.committee_session_id
)

SELECT *
FROM enhanced
