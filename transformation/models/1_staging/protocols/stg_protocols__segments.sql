-- Who spoke which part of a session's text | מי אמר איזה חלק מטקסט הישיבה
-- Grain: one row per speaker turn (session and position in it)

WITH source AS (
    SELECT *
    FROM {{ source('protocols', 'protocol_segments') }}
),

renamed AS (
    SELECT DISTINCT
        CAST(session_id AS INTEGER)    AS committee_session_id,
        CAST(segment_index AS INTEGER) AS turn_index,
        CAST(speaker_id AS INTEGER)    AS speaker_id,
        CAST(start_char AS INTEGER)    AS start_char,
        CAST(end_char AS INTEGER)      AS end_char
    FROM source
),

filtered AS (
    SELECT *
    FROM renamed
    WHERE end_char > start_char
),

enhanced AS (
    SELECT
        *
    FROM filtered
)

SELECT *
FROM enhanced
