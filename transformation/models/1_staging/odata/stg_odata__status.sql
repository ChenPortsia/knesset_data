-- Status codes for bills, queries, sessions and more | קודי סטטוס להצעות חוק, שאילתות, ישיבות ועוד
-- Grain: one row per status

WITH source AS (
    SELECT *
    FROM {{ source('odata', 'kns_status') }}
),

renamed AS (
    SELECT
        CAST(id AS INTEGER)                    AS status_id,
        CAST("desc" AS VARCHAR)                AS status_name,
        CAST(type_id AS INTEGER)               AS status_type_id,
        CAST(type_desc AS VARCHAR)             AS status_type,
        CAST(order_transition AS INTEGER)      AS order_transition,
        CAST(is_active AS BOOLEAN)             AS is_active,
        CAST(last_updated_date AS TIMESTAMPTZ) AS updated_at,
        CAST(_dlt_valid_from AS TIMESTAMPTZ)   AS loaded_at,
        CAST(_dlt_valid_to AS TIMESTAMPTZ)     AS valid_to
    FROM source
),

filtered AS (
    SELECT *
    FROM renamed
    WHERE {{ is_current('kns_status', 'status_id') }}
),

enhanced AS (
    SELECT
        *
    FROM filtered
)

SELECT * EXCLUDE (valid_to)
FROM enhanced
