-- People: MKs, ministers and other office holders | אנשים: חברי כנסת, שרים ונושאי תפקידים
-- Grain: one row per person

WITH source AS (
    SELECT *
    FROM {{ source('odata', 'kns_person') }}
),

renamed AS (
    SELECT
        CAST(id AS INTEGER)                    AS person_id,
        CAST(TRIM(first_name) AS VARCHAR)      AS first_name,
        CAST(TRIM(last_name) AS VARCHAR)       AS last_name,
        CAST(gender_id AS INTEGER)             AS gender_id,
        CAST(gender_desc AS VARCHAR)           AS gender_he,
        CAST(email AS VARCHAR)                 AS email,
        CAST(is_current AS BOOLEAN)            AS is_current,
        CAST(last_updated_date AS TIMESTAMPTZ) AS updated_at,
        CAST(_dlt_valid_from AS TIMESTAMPTZ)   AS loaded_at,
        CAST(_dlt_valid_to AS TIMESTAMPTZ)     AS valid_to
    FROM source
),

filtered AS (
    SELECT *
    FROM renamed
    WHERE {{ is_current('kns_person', 'person_id') }}
),

enhanced AS (
    SELECT
        *,
        CAST(first_name || ' ' || last_name AS VARCHAR)          AS full_name,
        CAST({{ code_label('gender', 'gender_id') }} AS VARCHAR) AS gender
    FROM filtered
)

SELECT * EXCLUDE (valid_to)
FROM enhanced
