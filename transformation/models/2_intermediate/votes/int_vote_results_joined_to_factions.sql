-- Each MK's vote with the faction they belonged to on the day of the vote | הצבעת כל ח"כ עם סיעתו ביום ההצבעה
-- Grain: one row per vote and MK (same as stg_odata__plenum_vote_result)
--
-- Two ways to find the faction, recorded in faction_match:
--   dated    a membership period covers the day of the vote
--   knesset  no dated period does, but the MK had exactly one faction in that Knesset.
--            Needed because on 2026-11-04 the source rewrote most 25th-Knesset membership
--            dates to 2026-11-03..10, so dated periods cover almost none of its votes.
--   none     neither: no membership, or several factions in that Knesset

WITH vote_results AS (
    SELECT *
    FROM {{ ref('stg_odata__plenum_vote_result') }}
),

memberships AS (
    SELECT *
    FROM {{ ref('int_faction_memberships_collapsed') }}
),

plenum_sessions AS (
    SELECT *
    FROM {{ ref('stg_odata__plenum_session') }}
),

factions_per_knesset AS (
    SELECT *
    FROM {{ ref('int_person_knesset_factions') }}
),

dated_joined AS (
    -- As-of join: the membership that covers the vote date (a period ends at the end of its finish day)
    SELECT
        vote_results.*,
        memberships.faction_id AS dated_faction_id,
        memberships.faction_name AS dated_faction_name,
        memberships.start_at AS membership_start_at
    FROM vote_results
    LEFT JOIN memberships
        ON vote_results.person_id = memberships.person_id
        AND vote_results.voted_at >= memberships.start_at
        AND vote_results.voted_at < COALESCE(memberships.finish_at + INTERVAL 1 DAY, TIMESTAMP '9999-12-31')
),

dated_deduplicated AS (
    -- Periods can overlap (faction splits, election handover): keep the most recent
    -- membership, so the grain stays one row per vote and MK
    SELECT *
    FROM dated_joined
    QUALIFY ROW_NUMBER() OVER (PARTITION BY vote_result_id ORDER BY membership_start_at DESC NULLS LAST) = 1
),

knesset_joined AS (
    SELECT
        dated_deduplicated.*,
        plenum_sessions.knesset_num,
        factions_per_knesset.faction_id AS knesset_faction_id,
        factions_per_knesset.faction_name AS knesset_faction_name
    FROM dated_deduplicated
    LEFT JOIN plenum_sessions
        ON dated_deduplicated.plenum_session_id = plenum_sessions.plenum_session_id
    LEFT JOIN factions_per_knesset
        ON dated_deduplicated.person_id = factions_per_knesset.person_id
        AND plenum_sessions.knesset_num = factions_per_knesset.knesset_num
),

enhanced AS (
    SELECT
        CAST(vote_result_id AS INTEGER) AS vote_result_id,
        CAST(vote_id AS INTEGER) AS vote_id,
        CAST(person_id AS INTEGER) AS person_id,
        CAST(COALESCE(dated_faction_id, knesset_faction_id) AS INTEGER) AS faction_id,
        CAST(COALESCE(dated_faction_name, knesset_faction_name) AS VARCHAR) AS faction_name,
        CAST(
            CASE
                WHEN dated_faction_id IS NOT NULL THEN 'dated'
                WHEN knesset_faction_id IS NOT NULL THEN 'knesset'
                ELSE 'none'
            END AS VARCHAR
        ) AS faction_match,
        CAST(knesset_num AS INTEGER) AS knesset_num,
        CAST(plenum_session_id AS INTEGER) AS plenum_session_id,
        CAST(voted_at AS TIMESTAMP) AS voted_at,
        CAST(result_code AS INTEGER) AS result_code,
        CAST(result AS VARCHAR) AS result,
        CAST(result IN ('for', 'against', 'abstain') AS BOOLEAN) AS took_part
    FROM knesset_joined
)

SELECT *
FROM enhanced
