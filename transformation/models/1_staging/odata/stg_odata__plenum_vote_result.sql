-- How each MK voted in each plenum vote | איך הצביע כל ח"כ בכל הצבעה במליאה
-- Grain: one row per vote and MK

WITH source AS (
    SELECT *
    FROM {{ source('odata', 'kns_plenum_vote_result') }}
),

renamed AS (
    SELECT
        CAST(id AS INTEGER)                              AS vote_result_id,
        CAST(vote_id AS INTEGER)                         AS vote_id,
        CAST(mk_id AS INTEGER)                           AS person_id,
        CAST(session_id AS INTEGER)                      AS plenum_session_id,
        CAST(item_id AS INTEGER)                         AS item_id,
        CAST({{ local_time('vote_date') }} AS TIMESTAMP) AS voted_at,
        CAST(result_code AS INTEGER)                     AS result_code,
        CAST(result_desc AS VARCHAR)                     AS result_he,
        CAST(last_updated_date AS TIMESTAMPTZ)           AS updated_at,
        CAST(_dlt_valid_from AS TIMESTAMPTZ)             AS loaded_at,
        CAST(_dlt_valid_to AS TIMESTAMPTZ)               AS valid_to
    FROM source
),

filtered AS (
    SELECT *
    FROM renamed
    WHERE {{ is_current('kns_plenum_vote_result', 'vote_result_id') }}
),

enhanced AS (
    SELECT
        *,
        CAST({{ code_label('vote_result', 'result_code') }} AS VARCHAR) AS result
    FROM filtered
)

SELECT * EXCLUDE (valid_to)
FROM enhanced
