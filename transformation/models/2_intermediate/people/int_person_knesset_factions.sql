-- Each MK's faction in each Knesset, when they had only one | הסיעה של כל ח"כ בכל כנסת, אם הייתה אחת
-- Grain: one row per person and Knesset
-- Used as a fallback when no dated membership covers a date: on 2026-11-04 the source
-- rewrote most 25th-Knesset membership dates, so dated periods miss most of that Knesset.

WITH memberships AS (
    SELECT *
    FROM {{ ref('int_faction_memberships_collapsed') }}
),

factions_per_knesset AS (
    SELECT
        person_id,
        knesset_num,
        COUNT(DISTINCT faction_id) AS factions,
        MIN(faction_id) AS faction_id,
        MIN(faction_name) AS faction_name
    FROM memberships
    GROUP BY person_id, knesset_num
),

enhanced AS (
    SELECT
        CAST(person_id AS INTEGER) AS person_id,
        CAST(knesset_num AS INTEGER) AS knesset_num,
        CAST(factions AS INTEGER) AS factions,
        CAST(CASE WHEN factions = 1 THEN faction_id END AS INTEGER) AS faction_id,
        CAST(CASE WHEN factions = 1 THEN faction_name END AS VARCHAR) AS faction_name
    FROM factions_per_knesset
)

SELECT *
FROM enhanced
