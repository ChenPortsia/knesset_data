-- Q8: Which MKs were members of more than one faction within the same Knesset?
-- Includes formal splits (a faction leaving an alliance) as well as personal switches.

WITH memberships AS (
    SELECT *
    FROM {{ ref('fct_faction_membership') }}
),

factions AS (
    SELECT *
    FROM {{ ref('dim_faction') }}
),

persons AS (
    SELECT *
    FROM {{ ref('dim_person') }}
),

filtered AS (
    -- Leave out the week-long handover after the 2026 election (new lists from 2026-11-03)
    SELECT *
    FROM memberships
    WHERE start_date < DATE '2026-11-03'
),

enhanced AS (
    SELECT
        filtered.knesset_num,
        persons.full_name,
        COUNT(DISTINCT filtered.faction_id) AS factions,
        STRING_AGG(factions.faction_name, ' -> ' ORDER BY filtered.start_date) AS faction_path
    FROM filtered
    INNER JOIN factions
        ON filtered.faction_id = factions.faction_id
    INNER JOIN persons
        ON filtered.person_id = persons.person_id
    GROUP BY filtered.knesset_num, persons.full_name
    HAVING COUNT(DISTINCT filtered.faction_id) > 1
)

SELECT *
FROM enhanced
ORDER BY knesset_num, full_name
