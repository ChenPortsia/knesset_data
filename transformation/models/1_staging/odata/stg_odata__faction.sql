-- Factions (parliamentary groups) per Knesset | סיעות בכל כנסת
-- Grain: one row per faction per Knesset

WITH source AS (
    SELECT *
    FROM {{ source('odata', 'kns_faction') }}
),

renamed AS (
    SELECT
        CAST(id AS INTEGER)                                AS faction_id,
        CAST(TRIM(name) AS VARCHAR)                        AS faction_name,
        CAST(knesset_num AS INTEGER)                       AS knesset_num,
        CAST({{ local_time('start_date') }} AS TIMESTAMP)  AS start_at,
        CAST({{ local_time('finish_date') }} AS TIMESTAMP) AS finish_at,
        CAST(is_current AS BOOLEAN)                        AS is_current,
        CAST(last_updated_date AS TIMESTAMPTZ)             AS updated_at,
        CAST(_dlt_valid_from AS TIMESTAMPTZ)               AS loaded_at,
        CAST(_dlt_valid_to AS TIMESTAMPTZ)                 AS valid_to
    FROM source
),

filtered AS (
    SELECT *
    FROM renamed
    WHERE {{ is_current('kns_faction', 'faction_id') }}
),

enhanced AS (
    SELECT
        *
    FROM filtered
)

SELECT * EXCLUDE (valid_to)
FROM enhanced
