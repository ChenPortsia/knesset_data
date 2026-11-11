-- How most of each faction voted in each vote | איך הצביע רוב כל סיעה בכל הצבעה
-- Grain: one row per vote and faction (factions with at least one MK taking part)
-- The majority is the most common result (for / against / abstain) among the faction's MKs
-- who took part. A tie has no majority. camp is the faction's camp on the day of the vote.

WITH vote_results AS (
    SELECT *
    FROM {{ ref('int_vote_results_joined_to_factions') }}
),

votes AS (
    SELECT *
    FROM {{ ref('int_votes_joined_to_items') }}
),

coalition_periods AS (
    SELECT *
    FROM {{ ref('int_coalition_periods') }}
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

results_ranked AS (
    SELECT
        *,
        MAX(mks) OVER (PARTITION BY vote_id, faction_id) AS top_mks
    FROM results_per_faction
),

majorities AS (
    SELECT
        vote_id,
        faction_id,
        CASE
            WHEN COUNT(*) FILTER (WHERE mks = top_mks) = 1
                THEN MAX(CASE WHEN mks = top_mks THEN result END)
        END AS majority_result,
        SUM(mks) AS mks_took_part,
        MAX(top_mks) AS mks_with_majority
    FROM results_ranked
    GROUP BY vote_id, faction_id
),

majorities_in_coalition AS (
    SELECT DISTINCT
        majorities.vote_id,
        majorities.faction_id
    FROM majorities
    INNER JOIN votes
        ON majorities.vote_id = votes.vote_id
    INNER JOIN coalition_periods
        ON majorities.faction_id = coalition_periods.faction_id
        AND votes.voted_at >= coalition_periods.start_at
        AND votes.voted_at < COALESCE(coalition_periods.finish_at + INTERVAL 1 DAY, TIMESTAMP '9999-12-31')
),

enhanced AS (
    SELECT
        CAST(MD5(CONCAT_WS('|', majorities.vote_id, majorities.faction_id)) AS VARCHAR) AS vote_faction_id,
        CAST(majorities.vote_id AS INTEGER) AS vote_id,
        CAST(majorities.faction_id AS INTEGER) AS faction_id,
        CAST(majorities.majority_result AS VARCHAR) AS majority_result,
        CAST(majorities.mks_took_part AS INTEGER) AS mks_took_part,
        CAST(majorities.mks_with_majority AS INTEGER) AS mks_with_majority,
        CAST(majorities.mks_with_majority < majorities.mks_took_part AS BOOLEAN) AS is_split,
        CAST(CASE WHEN majorities_in_coalition.vote_id IS NOT NULL THEN 'coalition' ELSE 'opposition' END AS VARCHAR) AS camp
    FROM majorities
    LEFT JOIN majorities_in_coalition
        ON majorities.vote_id = majorities_in_coalition.vote_id
        AND majorities.faction_id = majorities_in_coalition.faction_id
)

SELECT *
FROM enhanced
