-- Position types (MK, minister, committee chair...) | סוגי תפקידים (ח"כ, שר, יו"ר ועדה...)
-- Grain: one row per position type

WITH source AS (
    SELECT *
    FROM {{ source('odata', 'kns_position') }}
),

renamed AS (
    SELECT
        CAST(id AS INTEGER)                    AS position_id,
        CAST(description AS VARCHAR)           AS position_name,
        CAST(gender_id AS INTEGER)             AS gender_id,
        CAST(last_updated_date AS TIMESTAMPTZ) AS updated_at,
        CAST(_dlt_valid_from AS TIMESTAMPTZ)   AS loaded_at,
        CAST(_dlt_valid_to AS TIMESTAMPTZ)     AS valid_to
    FROM source
),

filtered AS (
    SELECT *
    FROM renamed
    WHERE {{ is_current('kns_position', 'position_id') }}
),

enhanced AS (
    SELECT
        *
    FROM filtered
)

SELECT * EXCLUDE (valid_to)
FROM enhanced
