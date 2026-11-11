-- Plenum votes with their totals | הצבעות במליאה עם סיכומי ההצבעה
-- Grain: one row per vote

WITH votes AS (
    SELECT *
    FROM {{ ref('int_votes_joined_to_items') }}
),

plenum_sessions AS (
    SELECT *
    FROM {{ ref('stg_odata__plenum_session') }}
),

vote_results AS (
    SELECT *
    FROM {{ ref('stg_odata__plenum_vote_result') }}
),

totals_per_vote AS (
    SELECT
        vote_id,
        COUNT(*) FILTER (WHERE result = 'for') AS votes_for,
        COUNT(*) FILTER (WHERE result = 'against') AS votes_against,
        COUNT(*) FILTER (WHERE result = 'abstain') AS votes_abstain,
        COUNT(*) FILTER (WHERE result IN ('for', 'against', 'abstain')) AS mks_took_part
    FROM vote_results
    GROUP BY vote_id
),

enhanced AS (
    SELECT
        CAST(votes.vote_id AS INTEGER) AS vote_id,
        CAST(votes.plenum_session_id AS INTEGER) AS plenum_session_id,
        CAST(plenum_sessions.knesset_num AS INTEGER) AS knesset_num,
        CAST(CAST(votes.voted_at AS DATE) AS DATE) AS vote_date,
        CAST(votes.voted_at AS TIMESTAMP) AS voted_at,
        CAST(votes.vote_title AS VARCHAR) AS vote_title,
        CAST(votes.vote_subject AS VARCHAR) AS vote_subject,
        CAST(votes.vote_method AS VARCHAR) AS vote_method,
        CAST(votes.is_no_confidence AS BOOLEAN) AS is_no_confidence,
        CAST(votes.item_type AS VARCHAR) AS item_type,
        CAST(votes.bill_id AS INTEGER) AS bill_id,
        CAST(COALESCE(totals_per_vote.votes_for, 0) AS INTEGER) AS votes_for,
        CAST(COALESCE(totals_per_vote.votes_against, 0) AS INTEGER) AS votes_against,
        CAST(COALESCE(totals_per_vote.votes_abstain, 0) AS INTEGER) AS votes_abstain,
        CAST(COALESCE(totals_per_vote.mks_took_part, 0) AS INTEGER) AS mks_took_part,
        CAST(totals_per_vote.votes_for > totals_per_vote.votes_against AS BOOLEAN) AS is_accepted
    FROM votes
    LEFT JOIN plenum_sessions
        ON votes.plenum_session_id = plenum_sessions.plenum_session_id
    LEFT JOIN totals_per_vote
        ON votes.vote_id = totals_per_vote.vote_id
)

SELECT *
FROM enhanced
