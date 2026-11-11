-- When each bill reached each plenum reading | מתי הגיעה כל הצעת חוק לכל קריאה במליאה
-- Grain: one row per bill and reading (tabled, preliminary, first, second_third)

WITH readings AS (
    SELECT *
    FROM {{ ref('int_bill_plenum_readings') }}
),

bills AS (
    SELECT *
    FROM {{ ref('stg_odata__bill') }}
),

enhanced AS (
    SELECT
        CAST(readings.bill_reading_id AS VARCHAR) AS bill_reading_id,
        CAST(readings.bill_id AS INTEGER) AS bill_id,
        CAST(bills.knesset_num AS INTEGER) AS knesset_num,
        CAST(readings.reading AS VARCHAR) AS reading,
        CAST(readings.reading_order AS INTEGER) AS reading_order,
        CAST(CAST(readings.first_at AS DATE) AS DATE) AS reading_date,
        CAST(CAST(readings.last_at AS DATE) AS DATE) AS last_agenda_date,
        CAST(readings.agenda_items AS INTEGER) AS agenda_items
    FROM readings
    INNER JOIN bills
        ON readings.bill_id = bills.bill_id
)

SELECT *
FROM enhanced
