-- An MK should not be in two factions at the same time. Overlaps would make the faction
-- of a vote ambiguous (int_vote_results_joined_to_factions then keeps the newest membership).
{{ config(severity='warn') }}

SELECT
    earlier.person_id,
    earlier.faction_id AS earlier_faction_id,
    later.faction_id AS later_faction_id,
    later.start_at AS overlap_start_at
FROM {{ ref('int_faction_memberships_collapsed') }} AS earlier
INNER JOIN {{ ref('int_faction_memberships_collapsed') }} AS later
    ON earlier.person_id = later.person_id
    AND earlier.membership_id != later.membership_id
    AND later.start_at > earlier.start_at
    AND later.start_at < COALESCE(earlier.finish_at, TIMESTAMP '9999-12-31')
