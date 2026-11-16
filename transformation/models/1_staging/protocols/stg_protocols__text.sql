-- The text of each committee session's protocol | הטקסט של פרוטוקול כל ישיבת ועדה
-- Grain: one row per committee session with a protocol

WITH source AS (
    SELECT *
    FROM {{ source('protocols', 'protocol_text') }}
),

renamed AS (
    SELECT
        CAST(session_id AS INTEGER) AS committee_session_id,
        CAST(text AS VARCHAR)       AS protocol_text,
        CAST(characters AS INTEGER) AS characters
    FROM source
),

filtered AS (
    -- A session loaded twice by mistake counts once
    SELECT *
    FROM renamed
    QUALIFY ROW_NUMBER() OVER (PARTITION BY committee_session_id ORDER BY characters DESC) = 1
),

enhanced AS (
    SELECT
        *
    FROM filtered
)

SELECT *
FROM enhanced
