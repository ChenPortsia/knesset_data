-- Items on a plenum session agenda; all Knessets | פריטים בסדר היום של ישיבת מליאה; כל הכנסות
-- Grain: one row per item per plenum session

WITH source AS (
    SELECT *
    FROM {{ source('odata', 'kns_plm_session_item') }}
),

renamed AS (
    SELECT
        CAST(id AS INTEGER)                    AS session_item_id,
        CAST(plenum_session_id AS INTEGER)     AS plenum_session_id,
        CAST(item_id AS INTEGER)               AS item_id,
        CAST(item_type_id AS INTEGER)          AS item_type_id,
        CAST(item_type_desc AS VARCHAR)        AS item_type,
        CAST(name AS VARCHAR)                  AS item_name,
        CAST(ordinal AS BIGINT)                AS ordinal,
        CAST(status_id AS INTEGER)             AS status_id,
        CAST(is_discussion AS BOOLEAN)         AS is_discussion,
        CAST(last_updated_date AS TIMESTAMPTZ) AS updated_at,
        CAST(_dlt_valid_from AS TIMESTAMPTZ)   AS loaded_at,
        CAST(_dlt_valid_to AS TIMESTAMPTZ)     AS valid_to
    FROM source
),

filtered AS (
    SELECT *
    FROM renamed
    WHERE {{ is_current('kns_plm_session_item', 'session_item_id') }}
),

enhanced AS (
    SELECT
        *
    FROM filtered
)

SELECT * EXCLUDE (valid_to)
FROM enhanced
