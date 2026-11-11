-- Each MK's vote compared with how most of their faction voted | השוואת הצבעת כל ח"כ לרוב סיעתו
-- Grain: one row per vote and MK (same as int_vote_results_joined_to_factions)
-- The faction majority is the most common result (for / against / abstain) among the
-- faction's MKs who took part. A tie has no majority.

WITH vote_results AS (
    SELECT *
    FROM {{ ref('int_vote_results_joined_to_factions') }}
),

filtered AS (
    SELECT *
    FROM vote_results
    WHERE took_part
      AND faction_id IS NOT NULL
),

results_per_faction AS (
    SELECT
        vote_id,
        faction_id,
        result,
        COUNT(*) AS mks
    FROM filtered
    GROUP BY vote_id, faction_id, result
),

faction_majorities AS (
    -- One row per vote and faction: the top result, unless tied
    SELECT
        vote_id,
        faction_id,
        CASE
            WHEN COUNT(*) FILTER (WHERE mks = max_mks) = 1
                THEN MAX(CASE WHEN mks = max_mks THEN result END)
        END AS majority_result,
        SUM(mks) AS mks_took_part
    FROM (
        SELECT
            *,
            MAX(mks) OVER (PARTITION BY vote_id, faction_id) AS max_mks
        FROM results_per_faction
    )
    GROUP BY vote_id, faction_id
),

enhanced AS (
    SELECT
        CAST(vote_results.vote_result_id AS INTEGER) AS vote_result_id,
        CAST(vote_results.vote_id AS INTEGER) AS vote_id,
        CAST(vote_results.person_id AS INTEGER) AS person_id,
        CAST(vote_results.faction_id AS INTEGER) AS faction_id,
        CAST(vote_results.faction_name AS VARCHAR) AS faction_name,
        CAST(vote_results.faction_match AS VARCHAR) AS faction_match,
        CAST(vote_results.knesset_num AS INTEGER) AS knesset_num,
        CAST(vote_results.plenum_session_id AS INTEGER) AS plenum_session_id,
        CAST(vote_results.voted_at AS TIMESTAMP) AS voted_at,
        CAST(vote_results.result_code AS INTEGER) AS result_code,
        CAST(vote_results.result AS VARCHAR) AS result,
        CAST(vote_results.took_part AS BOOLEAN) AS took_part,
        CAST(faction_majorities.majority_result AS VARCHAR) AS faction_majority_result,
        CAST(faction_majorities.mks_took_part AS INTEGER) AS faction_mks_took_part,
        CAST(
            CASE
                WHEN vote_results.took_part AND faction_majorities.majority_result IS NOT NULL
                    THEN vote_results.result = faction_majorities.majority_result
            END AS BOOLEAN
        ) AS voted_with_faction
    FROM vote_results
    LEFT JOIN faction_majorities
        ON vote_results.vote_id = faction_majorities.vote_id
        AND vote_results.faction_id = faction_majorities.faction_id
)

SELECT *
FROM enhanced
