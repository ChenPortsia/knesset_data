-- Plenum votes (one per vote held) | הצבעות במליאה
-- Grain: one row per vote

WITH source AS (
    SELECT *
    FROM {{ source('odata', 'kns_plenum_vote') }}
),

renamed AS (
    SELECT
        CAST(id AS INTEGER)                                   AS vote_id,
        CAST(session_id AS INTEGER)                           AS plenum_session_id,
        CAST(item_id AS INTEGER)                              AS item_id,
        CAST(ordinal AS INTEGER)                              AS ordinal,
        CAST({{ local_time('vote_date_time') }} AS TIMESTAMP) AS voted_at,
        CAST(vote_title AS VARCHAR)                           AS vote_title,
        CAST(vote_subject AS VARCHAR)                         AS vote_subject,
        CAST(vote_method_id AS INTEGER)                       AS vote_method_id,
        CAST(vote_method_desc AS VARCHAR)                     AS vote_method,
        CAST(vote_status_code AS INTEGER)                     AS vote_status_id,
        CAST(vote_status_desc AS VARCHAR)                     AS vote_status,
        CAST(is_no_confidence_in_gov AS BOOLEAN)              AS is_no_confidence,
        CAST(for_option_id AS INTEGER)                        AS for_option_id,
        CAST(for_option_desc AS VARCHAR)                      AS for_option,
        CAST(against_option_id AS INTEGER)                    AS against_option_id,
        CAST(against_option_desc AS VARCHAR)                  AS against_option,
        CAST(last_updated_date AS TIMESTAMPTZ)                AS updated_at,
        CAST(_dlt_valid_from AS TIMESTAMPTZ)                  AS loaded_at,
        CAST(_dlt_valid_to AS TIMESTAMPTZ)                    AS valid_to
    FROM source
),

filtered AS (
    SELECT *
    FROM renamed
    WHERE {{ is_current('kns_plenum_vote', 'vote_id') }}
),

enhanced AS (
    SELECT
        *
    FROM filtered
)

SELECT * EXCLUDE (valid_to)
FROM enhanced
