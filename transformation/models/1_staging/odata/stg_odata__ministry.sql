-- Government ministries | משרדי ממשלה
-- Grain: one row per ministry

WITH source AS (
    SELECT *
    FROM {{ source('odata', 'kns_gov_ministry') }}
),

renamed AS (
    SELECT
        CAST(id AS INTEGER)                    AS ministry_id,
        CAST(TRIM(name) AS VARCHAR)            AS ministry_name,
        CAST(category_id AS INTEGER)           AS category_id,
        CAST(category_name AS VARCHAR)         AS category_name,
        CAST(gov_id AS INTEGER)                AS gov_id,
        CAST(is_active AS BOOLEAN)             AS is_active,
        CAST(last_updated_date AS TIMESTAMPTZ) AS updated_at,
        CAST(_dlt_valid_from AS TIMESTAMPTZ)   AS loaded_at,
        CAST(_dlt_valid_to AS TIMESTAMPTZ)     AS valid_to
    FROM source
),

filtered AS (
    SELECT *
    FROM renamed
    WHERE {{ is_current('kns_gov_ministry', 'ministry_id') }}
),

enhanced AS (
    SELECT
        *
    FROM filtered
)

SELECT * EXCLUDE (valid_to)
FROM enhanced
