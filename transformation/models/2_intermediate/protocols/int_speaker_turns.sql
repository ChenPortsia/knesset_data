-- What each speaker said, turn by turn | מה אמר כל דובר, תור אחר תור
-- Grain: one row per speaker turn (session and position in it)
-- A turn is the piece of the session's text between two character positions.

WITH segments AS (
    SELECT *
    FROM {{ ref('stg_protocols__segments') }}
),

texts AS (
    SELECT *
    FROM {{ ref('stg_protocols__text') }}
),

enhanced AS (
    SELECT
        CAST(segments.committee_session_id AS INTEGER) AS committee_session_id,
        CAST(segments.turn_index AS INTEGER) AS turn_index,
        CAST(segments.speaker_id AS INTEGER) AS speaker_id,
        CAST(
            TRIM(REGEXP_REPLACE(
                SUBSTRING(texts.protocol_text, segments.start_char + 1, segments.end_char - segments.start_char),
                '\s+', ' ', 'g'
            )) AS VARCHAR
        ) AS turn_text
    FROM segments
    INNER JOIN texts
        ON segments.committee_session_id = texts.committee_session_id
)

SELECT *
FROM enhanced
WHERE turn_text <> ''
