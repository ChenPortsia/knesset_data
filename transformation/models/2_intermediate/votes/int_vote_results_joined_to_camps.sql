-- Each MK's vote with their camp, coalition or opposition, on the day | הצבעת כל ח"כ עם המחנה שלו ביום ההצבעה
-- Grain: one row per vote and MK
-- camp is 'coalition' if the MK's faction had a coalition period covering the vote date,
-- 'opposition' if not, and null if the MK's faction is unknown.

WITH vote_results AS (
    SELECT *
    FROM {{ ref('int_vote_results_compared_to_faction_majority') }}
),

coalition_periods AS (
    SELECT *
    FROM {{ ref('int_coalition_periods') }}
),

coalition_matches AS (
    -- One row per vote result that falls in a coalition period (periods of one faction can
    -- touch at a government handover, so collapse them)
    SELECT DISTINCT vote_results.vote_result_id
    FROM vote_results
    INNER JOIN coalition_periods
        ON vote_results.faction_id = coalition_periods.faction_id
        AND vote_results.voted_at >= coalition_periods.start_at
        AND vote_results.voted_at < COALESCE(coalition_periods.finish_at + INTERVAL 1 DAY, TIMESTAMP '9999-12-31')
),

enhanced AS (
    SELECT
        vote_results.*,
        CAST(
            CASE
                WHEN vote_results.faction_id IS NULL THEN NULL
                WHEN coalition_matches.vote_result_id IS NOT NULL THEN 'coalition'
                ELSE 'opposition'
            END AS VARCHAR
        ) AS camp
    FROM vote_results
    LEFT JOIN coalition_matches
        ON vote_results.vote_result_id = coalition_matches.vote_result_id
)

SELECT *
FROM enhanced
