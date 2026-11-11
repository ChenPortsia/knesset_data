-- When each bill reached each plenum reading | מתי הגיעה כל הצעת חוק לכל קריאה במליאה
-- Grain: one row per bill and reading (tabled, preliminary, first, second_third)
-- The plenum agenda records each bill with its status at the time ("in plenum for first
-- reading"); the bill_status_stages seed maps statuses to readings. Being on the agenda
-- for a reading means the reading was held, not that it passed.

WITH plenum_session_items AS (
    SELECT *
    FROM {{ ref('stg_odata__plenum_session_item') }}
),

plenum_sessions AS (
    SELECT *
    FROM {{ ref('stg_odata__plenum_session') }}
),

bill_status_stages AS (
    SELECT *
    FROM {{ ref('bill_status_stages') }}
),

bills AS (
    SELECT *
    FROM {{ ref('stg_odata__bill') }}
),

filtered AS (
    SELECT
        plenum_session_items.item_id AS bill_id,
        bill_status_stages.plenum_reading AS reading,
        plenum_sessions.start_at
    FROM plenum_session_items
    INNER JOIN plenum_sessions
        ON plenum_session_items.plenum_session_id = plenum_sessions.plenum_session_id
    INNER JOIN bill_status_stages
        ON plenum_session_items.status_id = bill_status_stages.status_id
    INNER JOIN bills  -- bills in scope only
        ON plenum_session_items.item_id = bills.bill_id
    WHERE plenum_session_items.item_type_id = 2
      AND bill_status_stages.plenum_reading IS NOT NULL
),

readings_per_bill AS (
    SELECT
        bill_id,
        reading,
        MIN(start_at) AS first_at,
        MAX(start_at) AS last_at,
        COUNT(*) AS agenda_items
    FROM filtered
    GROUP BY bill_id, reading
),

enhanced AS (
    SELECT
        CAST(MD5(CONCAT_WS('|', bill_id, reading)) AS VARCHAR) AS bill_reading_id,
        CAST(bill_id AS INTEGER) AS bill_id,
        CAST(reading AS VARCHAR) AS reading,
        CAST(CASE reading WHEN 'tabled' THEN 0 WHEN 'preliminary' THEN 1 WHEN 'first' THEN 2 WHEN 'second_third' THEN 3 END AS INTEGER) AS reading_order,
        CAST(first_at AS TIMESTAMP) AS first_at,
        CAST(last_at AS TIMESTAMP) AS last_at,
        CAST(agenda_items AS INTEGER) AS agenda_items
    FROM readings_per_bill
)

SELECT *
FROM enhanced
