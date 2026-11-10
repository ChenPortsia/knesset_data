-- Israeli laws in force or repealed; all Knessets | חוקי מדינת ישראל; כל הכנסות
-- Grain: one row per law

WITH source AS (
    SELECT *
    FROM {{ source('odata', 'kns_israel_law') }}
),

renamed AS (
    SELECT
        CAST(id AS INTEGER)                                            AS law_id,
        CAST(knesset_num AS INTEGER)                                   AS knesset_num,
        CAST(TRIM(name) AS VARCHAR)                                    AS law_name,
        CAST(is_basic_law AS BOOLEAN)                                  AS is_basic_law,
        CAST(is_favorite_law AS BOOLEAN)                               AS is_favorite_law,
        CAST(is_budget_law AS BOOLEAN)                                 AS is_budget_law,
        CAST(law_validity_id AS INTEGER)                               AS validity_id,
        CAST(law_validity_desc AS VARCHAR)                             AS validity,
        CAST({{ local_time('publication_date') }} AS TIMESTAMP)        AS published_at,
        CAST({{ local_time('latest_publication_date') }} AS TIMESTAMP) AS latest_published_at,
        CAST({{ local_time('validity_start_date') }} AS TIMESTAMP)     AS valid_from,
        CAST(validity_start_date_notes AS VARCHAR)                     AS valid_from_notes,
        CAST({{ local_time('validity_finish_date') }} AS TIMESTAMP)    AS valid_until,
        CAST(validity_finish_date_notes AS VARCHAR)                    AS valid_until_notes,
        CAST(last_updated_date AS TIMESTAMPTZ)                         AS updated_at,
        CAST(_dlt_valid_from AS TIMESTAMPTZ)                           AS loaded_at,
        CAST(_dlt_valid_to AS TIMESTAMPTZ)                             AS valid_to
    FROM source
),

filtered AS (
    SELECT *
    FROM renamed
    WHERE {{ is_current('kns_israel_law', 'law_id') }}
),

enhanced AS (
    SELECT
        *
    FROM filtered
)

SELECT * EXCLUDE (valid_to)
FROM enhanced
