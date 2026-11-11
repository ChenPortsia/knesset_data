-- At least 95% of MK votes should be matched to a faction. A lower rate means the faction
-- membership periods or the as-of join are wrong.
{{ config(severity='warn') }}

SELECT
    COUNT(*) AS vote_results,
    COUNT(faction_id) AS with_faction,
    ROUND(100.0 * COUNT(faction_id) / COUNT(*), 1) AS percent_with_faction
FROM {{ ref('int_vote_results_joined_to_factions') }}
HAVING COUNT(faction_id) < 0.95 * COUNT(*)
