-- Bills with their current stage and outcome | הצעות חוק עם השלב והתוצאה הנוכחיים
-- Grain: one row per bill
-- The stage comes from the bill_status_stages seed (status -> stage, outcome).

WITH bills AS (
    SELECT *
    FROM {{ ref('stg_odata__bill') }}
),

statuses AS (
    SELECT *
    FROM {{ ref('stg_odata__status') }}
),

bill_status_stages AS (
    SELECT *
    FROM {{ ref('bill_status_stages') }}
),

enhanced AS (
    SELECT
        CAST(bills.bill_id AS INTEGER) AS bill_id,
        CAST(bills.knesset_num AS INTEGER) AS knesset_num,
        CAST(bills.bill_name AS VARCHAR) AS bill_name,
        CAST(bills.origin AS VARCHAR) AS origin,
        CAST(bills.committee_id AS INTEGER) AS committee_id,
        CAST(bills.status_id AS INTEGER) AS status_id,
        CAST(statuses.status_name AS VARCHAR) AS status_he,
        CAST(bill_status_stages.status_en AS VARCHAR) AS status_en,
        CAST(bill_status_stages.stage AS VARCHAR) AS stage,
        CAST(bill_status_stages.stage_order AS INTEGER) AS stage_order,
        CAST(bill_status_stages.outcome AS VARCHAR) AS outcome,
        CAST(bill_status_stages.outcome = 'passed' AS BOOLEAN) AS is_passed,
        CAST(bills.published_at AS TIMESTAMP) AS published_at,
        CAST(bills.is_continuation_bill AS BOOLEAN) AS is_continuation_bill,
        CAST(bills.updated_at AS TIMESTAMPTZ) AS updated_at
    FROM bills
    LEFT JOIN statuses
        ON bills.status_id = statuses.status_id
    LEFT JOIN bill_status_stages
        ON bills.status_id = bill_status_stages.status_id
)

SELECT *
FROM enhanced
