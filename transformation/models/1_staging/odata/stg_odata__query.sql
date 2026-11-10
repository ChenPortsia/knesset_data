-- Parliamentary queries from MKs to ministers | שאילתות של חברי כנסת לשרים
-- Grain: one row per query

WITH source AS (
    SELECT *
    FROM {{ source('odata', 'kns_query') }}
),

renamed AS (
    SELECT
        CAST(id AS INTEGER)                                        AS query_id,
        CAST(knesset_num AS INTEGER)                               AS knesset_num,
        CAST(number AS INTEGER)                                    AS query_number,
        CAST(TRIM(name) AS VARCHAR)                                AS query_name,
        CAST(type_id AS INTEGER)                                   AS query_type_id,
        CAST(type_desc AS VARCHAR)                                 AS query_type,
        CAST(status_id AS INTEGER)                                 AS status_id,
        CAST(person_id AS INTEGER)                                 AS person_id,
        CAST(gov_ministry_id AS INTEGER)                           AS ministry_id,
        CAST({{ local_time('submit_date') }} AS TIMESTAMP)         AS submitted_at,
        CAST({{ local_time('reply_date_planned') }} AS TIMESTAMP)  AS reply_planned_at,
        CAST({{ local_time('reply_minister_date') }} AS TIMESTAMP) AS replied_at,
        CAST(last_updated_date AS TIMESTAMPTZ)                     AS updated_at,
        CAST(_dlt_valid_from AS TIMESTAMPTZ)                       AS loaded_at,
        CAST(_dlt_valid_to AS TIMESTAMPTZ)                         AS valid_to
    FROM source
),

filtered AS (
    SELECT *
    FROM renamed
    WHERE {{ is_current('kns_query', 'query_id') }}
),

enhanced AS (
    SELECT
        *
    FROM filtered
)

SELECT * EXCLUDE (valid_to)
FROM enhanced
