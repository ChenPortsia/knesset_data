-- Plenum sessions | ישיבות מליאה
-- Grain: one row per plenum session

WITH source AS (
    SELECT *
    FROM {{ source('odata', 'kns_plenum_session') }}
),

renamed AS (
    SELECT
        CAST(id AS INTEGER)                                AS plenum_session_id,
        CAST(knesset_num AS INTEGER)                       AS knesset_num,
        CAST(number AS INTEGER)                            AS session_number,
        CAST(name AS VARCHAR)                              AS session_name,
        CAST(is_special_meeting AS BOOLEAN)                AS is_special_meeting,
        CAST({{ local_time('start_date') }} AS TIMESTAMP)  AS start_at,
        CAST({{ local_time('finish_date') }} AS TIMESTAMP) AS finish_at,
        CAST(last_updated_date AS TIMESTAMPTZ)             AS updated_at,
        CAST(_dlt_valid_from AS TIMESTAMPTZ)               AS loaded_at,
        CAST(_dlt_valid_to AS TIMESTAMPTZ)                 AS valid_to
    FROM source
),

filtered AS (
    SELECT *
    FROM renamed
    WHERE {{ is_current('kns_plenum_session', 'plenum_session_id') }}
),

enhanced AS (
    SELECT
        *
    FROM filtered
)

SELECT * EXCLUDE (valid_to)
FROM enhanced
