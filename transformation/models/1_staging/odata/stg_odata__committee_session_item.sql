-- Items on a committee session agenda (bills, queries, topics); all Knessets | פריטים בסדר היום של ישיבת ועדה; כל הכנסות
-- Grain: one row per item per committee session

WITH source AS (
    SELECT *
    FROM {{ source('odata', 'kns_cmt_session_item') }}
),

renamed AS (
    SELECT
        CAST(id AS INTEGER)                    AS session_item_id,
        CAST(committee_session_id AS INTEGER)  AS committee_session_id,
        CAST(item_id AS INTEGER)               AS item_id,
        CAST(item_type_id AS INTEGER)          AS item_type_id,
        CAST(name AS VARCHAR)                  AS item_name,
        CAST(ordinal AS INTEGER)               AS ordinal,
        CAST(status_id AS INTEGER)             AS status_id,
        CAST(last_updated_date AS TIMESTAMPTZ) AS updated_at,
        CAST(_dlt_valid_from AS TIMESTAMPTZ)   AS loaded_at,
        CAST(_dlt_valid_to AS TIMESTAMPTZ)     AS valid_to
    FROM source
),

filtered AS (
    SELECT *
    FROM renamed
    WHERE {{ is_current('kns_cmt_session_item', 'session_item_id') }}
),

enhanced AS (
    SELECT
        *
    FROM filtered
)

SELECT * EXCLUDE (valid_to)
FROM enhanced
