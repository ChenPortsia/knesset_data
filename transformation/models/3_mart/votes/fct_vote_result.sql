-- How each MK voted in each plenum vote, with their faction | איך הצביע כל ח"כ בכל הצבעה, עם סיעתו
-- Grain: one row per vote and MK

WITH vote_results AS (
    SELECT *
    FROM {{ ref('int_vote_results_compared_to_faction_majority') }}
),

enhanced AS (
    SELECT
        CAST(vote_result_id AS INTEGER) AS vote_result_id,
        CAST(vote_id AS INTEGER) AS vote_id,
        CAST(person_id AS INTEGER) AS person_id,
        CAST(faction_id AS INTEGER) AS faction_id,
        CAST(faction_match AS VARCHAR) AS faction_match,
        CAST(knesset_num AS INTEGER) AS knesset_num,
        CAST(CAST(voted_at AS DATE) AS DATE) AS vote_date,
        CAST(voted_at AS TIMESTAMP) AS voted_at,
        CAST(result AS VARCHAR) AS result,
        CAST(took_part AS BOOLEAN) AS took_part,
        CAST(faction_majority_result AS VARCHAR) AS faction_majority_result,
        CAST(voted_with_faction AS BOOLEAN) AS voted_with_faction
    FROM vote_results
)

SELECT *
FROM enhanced
