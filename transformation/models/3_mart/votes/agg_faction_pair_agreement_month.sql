-- How often each pair of factions voted the same way, per month | באיזו תדירות הצביעו כל שתי סיעות באותו אופן, לפי חודש
-- Grain: one row per month, pair of factions (faction_a_id < faction_b_id) and camp pair
-- camp_pair is the two factions' camps at the time of each vote: coalition-coalition,
-- coalition-opposition or opposition-opposition (a pair can have two in a month when a
-- faction joins or leaves the coalition).
-- Two factions agree on a vote when their majorities (int_faction_vote_majorities) are the
-- same. Only votes where both factions had a majority count.

WITH faction_majorities AS (
    SELECT *
    FROM {{ ref('int_faction_vote_majorities') }}
),

votes AS (
    SELECT *
    FROM {{ ref('int_votes_joined_to_items') }}
),

factions AS (
    SELECT *
    FROM {{ ref('stg_odata__faction') }}
),

filtered AS (
    SELECT *
    FROM faction_majorities
    WHERE majority_result IS NOT NULL
),

pairs AS (
    SELECT
        faction_a.vote_id,
        faction_a.faction_id AS faction_a_id,
        faction_b.faction_id AS faction_b_id,
        faction_a.majority_result = faction_b.majority_result AS agreed,
        CASE
            WHEN faction_a.camp = 'coalition' AND faction_b.camp = 'coalition' THEN 'coalition-coalition'
            WHEN faction_a.camp = 'opposition' AND faction_b.camp = 'opposition' THEN 'opposition-opposition'
            ELSE 'coalition-opposition'
        END AS camp_pair
    FROM filtered AS faction_a
    INNER JOIN filtered AS faction_b
        ON faction_a.vote_id = faction_b.vote_id
        AND faction_a.faction_id < faction_b.faction_id
),

pairs_per_month AS (
    SELECT
        DATE_TRUNC('month', votes.voted_at) AS month_start,
        pairs.faction_a_id,
        pairs.faction_b_id,
        pairs.camp_pair,
        COUNT(*) AS votes,
        COUNT(*) FILTER (WHERE pairs.agreed) AS agreed
    FROM pairs
    INNER JOIN votes
        ON pairs.vote_id = votes.vote_id
    GROUP BY 1, 2, 3, 4
),

enhanced AS (
    SELECT
        CAST(MD5(CONCAT_WS('|', pairs_per_month.month_start, pairs_per_month.faction_a_id, pairs_per_month.faction_b_id, pairs_per_month.camp_pair)) AS VARCHAR) AS pair_month_id,
        CAST(pairs_per_month.month_start AS DATE) AS month_start,
        CAST(STRFTIME(pairs_per_month.month_start, '%Y-%m') AS VARCHAR) AS year_month,
        CAST(faction_a.knesset_num AS INTEGER) AS knesset_num,
        CAST(pairs_per_month.faction_a_id AS INTEGER) AS faction_a_id,
        CAST(faction_a.faction_name AS VARCHAR) AS faction_a_name,
        CAST(pairs_per_month.faction_b_id AS INTEGER) AS faction_b_id,
        CAST(faction_b.faction_name AS VARCHAR) AS faction_b_name,
        CAST(pairs_per_month.camp_pair AS VARCHAR) AS camp_pair,
        CAST(pairs_per_month.votes AS INTEGER) AS votes,
        CAST(pairs_per_month.agreed AS INTEGER) AS agreed,
        CAST(ROUND(100.0 * pairs_per_month.agreed / pairs_per_month.votes, 1) AS DOUBLE) AS agreement_percent
    FROM pairs_per_month
    LEFT JOIN factions AS faction_a
        ON pairs_per_month.faction_a_id = faction_a.faction_id
    LEFT JOIN factions AS faction_b
        ON pairs_per_month.faction_b_id = faction_b.faction_id
)

SELECT *
FROM enhanced
