-- Knesset committees per Knesset | ועדות הכנסת בכל כנסת
-- Grain: one row per committee per Knesset

WITH source AS (
    SELECT *
    FROM {{ source('odata', 'kns_committee') }}
),

renamed AS (
    SELECT
        CAST(id AS INTEGER)                                AS committee_id,
        CAST(TRIM(name) AS VARCHAR)                        AS committee_name,
        CAST(knesset_num AS INTEGER)                       AS knesset_num,
        CAST(category_id AS SMALLINT)                      AS category_id,
        CAST(category_desc AS VARCHAR)                     AS category_name,
        CAST(committee_type_id AS INTEGER)                 AS committee_type_id,
        CAST(committee_type_desc AS VARCHAR)               AS committee_type,
        CAST(additional_type_id AS INTEGER)                AS additional_type_id,
        CAST(additional_type_desc AS VARCHAR)              AS additional_type,
        CAST(parent_committee_id AS INTEGER)               AS parent_committee_id,
        CAST(committee_parent_name AS VARCHAR)             AS parent_committee_name,
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
    WHERE {{ is_current('kns_committee', 'committee_id') }}
),

enhanced AS (
    SELECT
        *
    FROM filtered
)

SELECT * EXCLUDE (valid_to)
FROM enhanced
