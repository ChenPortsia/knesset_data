-- Bills (proposed laws) | הצעות חוק
-- Grain: one row per bill

WITH source AS (
    SELECT *
    FROM {{ source('odata', 'kns_bill') }}
),

renamed AS (
    SELECT
        CAST(id AS INTEGER)                                     AS bill_id,
        CAST(knesset_num AS INTEGER)                            AS knesset_num,
        CAST(TRIM(name) AS VARCHAR)                             AS bill_name,
        CAST(type_id AS INTEGER)                                AS bill_type_id,
        CAST(type_desc AS VARCHAR)                              AS bill_type,
        CAST(sub_type_id AS INTEGER)                            AS origin_id,
        CAST(sub_type_desc AS VARCHAR)                          AS origin_he,
        CAST(private_number AS INTEGER)                         AS private_number,
        CAST(number AS INTEGER)                                 AS bill_number,
        CAST(committee_id AS INTEGER)                           AS committee_id,
        CAST(status_id AS INTEGER)                              AS status_id,
        CAST(postponement_reason_id AS INTEGER)                 AS postponement_reason_id,
        CAST(postponement_reason_desc AS VARCHAR)               AS postponement_reason,
        CAST(is_continuation_bill AS BOOLEAN)                   AS is_continuation_bill,
        CAST({{ local_time('publication_date') }} AS TIMESTAMP) AS published_at,
        CAST(publication_series_id AS INTEGER)                  AS publication_series_id,
        CAST(publication_series_desc AS VARCHAR)                AS publication_series,
        CAST(publication_series_first_call_id AS INTEGER)       AS first_call_series_id,
        CAST(publication_series_first_call_desc AS VARCHAR)     AS first_call_series,
        CAST(magazine_number AS VARCHAR)                        AS magazine_number,
        CAST(page_number AS VARCHAR)                            AS page_number,
        CAST(summary_law AS VARCHAR)                            AS summary,
        CAST(last_updated_date AS TIMESTAMPTZ)                  AS updated_at,
        CAST(_dlt_valid_from AS TIMESTAMPTZ)                    AS loaded_at,
        CAST(_dlt_valid_to AS TIMESTAMPTZ)                      AS valid_to
    FROM source
),

filtered AS (
    SELECT *
    FROM renamed
    WHERE {{ is_current('kns_bill', 'bill_id') }}
),

enhanced AS (
    SELECT
        *,
        CAST({{ code_label('bill_origin', 'origin_id') }} AS VARCHAR) AS origin
    FROM filtered
)

SELECT * EXCLUDE (valid_to)
FROM enhanced
