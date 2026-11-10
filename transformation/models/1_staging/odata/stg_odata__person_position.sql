-- Who held which position, when: MK in a faction, minister, committee member | מי כיהן באיזה תפקיד ומתי: ח"כ בסיעה, שר, חבר ועדה
-- Grain: one row per person, position and period

WITH source AS (
    SELECT *
    FROM {{ source('odata', 'kns_person_to_position') }}
),

renamed AS (
    SELECT
        CAST(id AS INTEGER)                                AS person_position_id,
        CAST(person_id AS INTEGER)                         AS person_id,
        CAST(position_id AS INTEGER)                       AS position_id,
        CAST(knesset_num AS INTEGER)                       AS knesset_num,
        CAST(faction_id AS INTEGER)                        AS faction_id,
        CAST(faction_name AS VARCHAR)                      AS faction_name,
        CAST(committee_id AS INTEGER)                      AS committee_id,
        CAST(committee_name AS VARCHAR)                    AS committee_name,
        CAST(gov_ministry_id AS INTEGER)                   AS ministry_id,
        CAST(gov_ministry_name AS VARCHAR)                 AS ministry_name,
        CAST(government_num AS INTEGER)                    AS government_num,
        CAST(duty_desc AS VARCHAR)                         AS duty,
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
    WHERE {{ is_current('kns_person_to_position', 'person_position_id') }}
),

enhanced AS (
    SELECT
        *
    FROM filtered
)

SELECT * EXCLUDE (valid_to)
FROM enhanced
