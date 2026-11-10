-- Committee sessions (meetings) | ישיבות ועדה
-- Grain: one row per committee session

WITH source AS (
    SELECT *
    FROM {{ source('odata', 'kns_committee_session') }}
),

renamed AS (
    SELECT
        CAST(id AS INTEGER)                                AS committee_session_id,
        CAST(committee_id AS INTEGER)                      AS committee_id,
        CAST(knesset_num AS INTEGER)                       AS knesset_num,
        CAST(number AS INTEGER)                            AS session_number,
        CAST(type_id AS INTEGER)                           AS session_type_id,
        CAST(type_desc AS VARCHAR)                         AS session_type,
        CAST(status_id AS INTEGER)                         AS status_id,
        CAST(status_desc AS VARCHAR)                       AS status,
        CAST(location AS VARCHAR)                          AS location,
        CAST(session_url AS VARCHAR)                       AS session_url,
        CAST(broadcast_url AS VARCHAR)                     AS broadcast_url,
        CAST(note AS VARCHAR)                              AS note,
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
    WHERE {{ is_current('kns_committee_session', 'committee_session_id') }}
),

enhanced AS (
    SELECT
        *
    FROM filtered
)

SELECT * EXCLUDE (valid_to)
FROM enhanced
