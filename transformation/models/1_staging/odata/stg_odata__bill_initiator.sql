-- MKs who initiated or joined a bill; all Knessets | חברי כנסת שיזמו או הצטרפו להצעת חוק; כל הכנסות
-- Grain: one row per bill and person

WITH source AS (
    SELECT *
    FROM {{ source('odata', 'kns_bill_initiator') }}
),

renamed AS (
    SELECT
        CAST(id AS INTEGER)                    AS bill_initiator_id,
        CAST(bill_id AS INTEGER)               AS bill_id,
        CAST(person_id AS INTEGER)             AS person_id,
        CAST(is_initiator AS BOOLEAN)          AS is_initiator,
        CAST(ordinal AS INTEGER)               AS ordinal,
        CAST(last_updated_date AS TIMESTAMPTZ) AS updated_at,
        CAST(_dlt_valid_from AS TIMESTAMPTZ)   AS loaded_at,
        CAST(_dlt_valid_to AS TIMESTAMPTZ)     AS valid_to
    FROM source
),

filtered AS (
    SELECT *
    FROM renamed
    WHERE {{ is_current('kns_bill_initiator', 'bill_initiator_id') }}
),

enhanced AS (
    SELECT
        *
    FROM filtered
)

SELECT * EXCLUDE (valid_to)
FROM enhanced
