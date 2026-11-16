-- Speakers of each session, with the name taken apart | הדוברים בכל ישיבה, עם פירוק השם
-- Grain: one row per committee session and speaker
-- The protocol marks MKs in the name: 'ינון אזולאי (ש"ס)' or 'היו"ר משה גפני'.

WITH source AS (
    SELECT *
    FROM {{ source('protocols', 'protocol_speakers') }}
),

renamed AS (
    SELECT DISTINCT
        CAST(session_id AS INTEGER)          AS committee_session_id,
        CAST(speaker_id AS INTEGER)          AS speaker_id,
        CAST(TRIM(speaker_name) AS VARCHAR)  AS speaker_name
    FROM source
),

filtered AS (
    -- A few files repeat a speaker id with different names: keep the shortest (the cleanest)
    SELECT *
    FROM renamed
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY committee_session_id, speaker_id
        ORDER BY LENGTH(speaker_name), speaker_name
    ) = 1
),

enhanced AS (
    SELECT
        *,
        CAST(speaker_name LIKE 'היו"ר %' AS BOOLEAN) AS is_chair,
        CAST(NULLIF(TRIM(REGEXP_EXTRACT(speaker_name, '\(([^)]*)\)\s*$', 1)), '') AS VARCHAR) AS faction_text,
        -- The name alone: no chair title, no faction in brackets
        CAST(
            TRIM(REGEXP_REPLACE(REGEXP_REPLACE(speaker_name, '^היו"ר\s+', ''), '\s*\([^)]*\)\s*$', ''))
            AS VARCHAR
        ) AS person_name
    FROM filtered
)

SELECT *
FROM enhanced
