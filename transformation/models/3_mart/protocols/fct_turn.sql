-- What was said in committee, turn by turn, with who said it | מה נאמר בוועדות, תור אחר תור, ומי אמר
-- Grain: one row per speaker turn (committee session and position in it)

WITH turns AS (
    SELECT *
    FROM {{ ref('int_speaker_turns') }}
),

speaker_links AS (
    SELECT *
    FROM {{ ref('int_speaker_links') }}
),

committee_sessions AS (
    SELECT *
    FROM {{ ref('stg_odata__committee_session') }}
),

memberships AS (
    SELECT *
    FROM {{ ref('int_faction_memberships_collapsed') }}
),

knesset_factions AS (
    SELECT *
    FROM {{ ref('int_person_knesset_factions') }}
),

coalition_periods AS (
    SELECT *
    FROM {{ ref('int_coalition_periods') }}
),

speakers AS (
    -- One row per session and linked speaker, with the session's time
    SELECT
        speaker_links.committee_session_id,
        speaker_links.speaker_id,
        speaker_links.person_id,
        committee_sessions.knesset_num,
        committee_sessions.start_at
    FROM speaker_links
    INNER JOIN committee_sessions
        ON speaker_links.committee_session_id = committee_sessions.committee_session_id
    WHERE speaker_links.person_id IS NOT NULL
),

speakers_dated AS (
    -- The speaker's faction membership covering the session
    SELECT
        speakers.committee_session_id,
        speakers.speaker_id,
        memberships.faction_id
    FROM speakers
    INNER JOIN memberships
        ON speakers.person_id = memberships.person_id
        AND speakers.start_at >= memberships.start_at
        AND speakers.start_at < COALESCE(memberships.finish_at + INTERVAL 1 DAY, TIMESTAMP '9999-12-31')
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY speakers.committee_session_id, speakers.speaker_id
        ORDER BY memberships.start_at DESC
    ) = 1
),

speaker_factions AS (
    -- Dated membership first; else the MK's only faction in that Knesset (as for votes)
    SELECT
        speakers.committee_session_id,
        speakers.speaker_id,
        speakers.start_at,
        COALESCE(speakers_dated.faction_id, knesset_factions.faction_id) AS faction_id
    FROM speakers
    LEFT JOIN speakers_dated
        ON speakers.committee_session_id = speakers_dated.committee_session_id
        AND speakers.speaker_id = speakers_dated.speaker_id
    LEFT JOIN knesset_factions
        ON speakers.person_id = knesset_factions.person_id
        AND speakers.knesset_num = knesset_factions.knesset_num
),

speakers_in_coalition AS (
    SELECT DISTINCT
        speaker_factions.committee_session_id,
        speaker_factions.speaker_id
    FROM speaker_factions
    INNER JOIN coalition_periods
        ON speaker_factions.faction_id = coalition_periods.faction_id
        AND speaker_factions.start_at >= coalition_periods.start_at
        AND speaker_factions.start_at < COALESCE(coalition_periods.finish_at + INTERVAL 1 DAY, TIMESTAMP '9999-12-31')
),

enhanced AS (
    SELECT
        CAST(turns.committee_session_id || '-' || turns.turn_index AS VARCHAR) AS turn_id,
        CAST(turns.committee_session_id AS INTEGER) AS committee_session_id,
        CAST(turns.turn_index AS INTEGER) AS turn_index,
        CAST(committee_sessions.committee_id AS INTEGER) AS committee_id,
        CAST(committee_sessions.knesset_num AS INTEGER) AS knesset_num,
        CAST(CAST(committee_sessions.start_at AS DATE) AS DATE) AS session_date,
        CAST(speaker_links.speaker_name AS VARCHAR) AS speaker_name,
        CAST(speaker_links.speaker_kind AS VARCHAR) AS speaker_kind,
        CAST(COALESCE(speaker_links.is_chair, FALSE) AS BOOLEAN) AS is_chair,
        CAST(speaker_links.person_id AS INTEGER) AS person_id,
        CAST(speaker_links.link_method AS VARCHAR) AS link_method,
        CAST(speaker_factions.faction_id AS INTEGER) AS faction_id,
        CAST(
            CASE
                WHEN speakers_in_coalition.speaker_id IS NOT NULL THEN 'coalition'
                WHEN speaker_factions.faction_id IS NOT NULL THEN 'opposition'
            END AS VARCHAR
        ) AS camp,
        CAST(turns.turn_text AS VARCHAR) AS turn_text,
        CAST(LENGTH(turns.turn_text) AS INTEGER) AS characters,
        CAST(LENGTH(turns.turn_text) - LENGTH(REPLACE(turns.turn_text, ' ', '')) + 1 AS INTEGER) AS words
    FROM turns
    INNER JOIN committee_sessions
        ON turns.committee_session_id = committee_sessions.committee_session_id
    LEFT JOIN speaker_links
        ON turns.committee_session_id = speaker_links.committee_session_id
        AND turns.speaker_id = speaker_links.speaker_id
    LEFT JOIN speaker_factions
        ON turns.committee_session_id = speaker_factions.committee_session_id
        AND turns.speaker_id = speaker_factions.speaker_id
    LEFT JOIN speakers_in_coalition
        ON turns.committee_session_id = speakers_in_coalition.committee_session_id
        AND turns.speaker_id = speakers_in_coalition.speaker_id
)

SELECT *
FROM enhanced
