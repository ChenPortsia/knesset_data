-- Each MK's vote with the faction they belonged to on the day of the vote | הצבעת כל ח"כ עם סיעתו ביום ההצבעה
-- Grain: one row per vote and MK (same as stg_odata__plenum_vote_result)

WITH vote_results AS (
    SELECT *
    FROM {{ ref('stg_odata__plenum_vote_result') }}
),

memberships AS (
    SELECT *
    FROM {{ ref('int_faction_memberships_collapsed') }}
),

joined AS (
    -- As-of join: the membership that covers the vote date (a period ends at the end of its finish day)
    SELECT
        vote_results.*,
        memberships.faction_id,
        memberships.faction_name,
        memberships.start_at AS membership_start_at
    FROM vote_results
    LEFT JOIN memberships
        ON vote_results.person_id = memberships.person_id
        AND vote_results.voted_at >= memberships.start_at
        AND vote_results.voted_at < COALESCE(memberships.finish_at + INTERVAL 1 DAY, TIMESTAMP '9999-12-31')
),

deduplicated AS (
    -- If source periods overlap across factions, keep the most recent membership,
    -- so the grain stays one row per vote and MK
    SELECT *
    FROM joined
    QUALIFY ROW_NUMBER() OVER (PARTITION BY vote_result_id ORDER BY membership_start_at DESC NULLS LAST) = 1
),

enhanced AS (
    SELECT
        CAST(vote_result_id AS INTEGER) AS vote_result_id,
        CAST(vote_id AS INTEGER) AS vote_id,
        CAST(person_id AS INTEGER) AS person_id,
        CAST(faction_id AS INTEGER) AS faction_id,
        CAST(faction_name AS VARCHAR) AS faction_name,
        CAST(plenum_session_id AS INTEGER) AS plenum_session_id,
        CAST(voted_at AS TIMESTAMP) AS voted_at,
        CAST(result_code AS INTEGER) AS result_code,
        CAST(result AS VARCHAR) AS result,
        CAST(result IN ('for', 'against', 'abstain') AS BOOLEAN) AS took_part
    FROM deduplicated
)

SELECT *
FROM enhanced
