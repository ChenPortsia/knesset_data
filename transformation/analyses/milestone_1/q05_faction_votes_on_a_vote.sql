-- Q5: How did each faction vote on a given vote?
-- Set the vote with: dbt compile --vars '{vote_id: 12345}'. Default: the 25th Knesset's
-- vote with the most MKs taking part.

WITH vote_results AS (
    SELECT *
    FROM {{ ref('fct_vote_result') }}
),

votes AS (
    SELECT *
    FROM {{ ref('fct_plenum_vote') }}
),

factions AS (
    SELECT *
    FROM {{ ref('dim_faction') }}
),

chosen_vote AS (
    SELECT vote_id, vote_title, vote_subject, vote_date
    FROM votes
    {% if var('vote_id', none) %}
    WHERE vote_id = {{ var('vote_id') }}
    {% else %}
    WHERE knesset_num = 25
    ORDER BY mks_took_part DESC, vote_date DESC
    LIMIT 1
    {% endif %}
),

enhanced AS (
    SELECT
        chosen_vote.vote_title,
        chosen_vote.vote_date,
        COALESCE(factions.faction_name, '(no faction)') AS faction_name,
        COUNT(*) FILTER (WHERE vote_results.result = 'for') AS votes_for,
        COUNT(*) FILTER (WHERE vote_results.result = 'against') AS votes_against,
        COUNT(*) FILTER (WHERE vote_results.result = 'abstain') AS votes_abstain,
        COUNT(*) FILTER (WHERE NOT vote_results.took_part) AS did_not_vote
    FROM chosen_vote
    INNER JOIN vote_results
        ON chosen_vote.vote_id = vote_results.vote_id
    LEFT JOIN factions
        ON vote_results.faction_id = factions.faction_id
    GROUP BY ALL
)

SELECT *
FROM enhanced
ORDER BY votes_for DESC, votes_against DESC
