-- Factions (parliamentary groups) per Knesset | סיעות בכל כנסת
-- Grain: one row per faction (a faction belongs to one Knesset)

WITH factions AS (
    SELECT *
    FROM {{ ref('stg_odata__faction') }}
),

memberships AS (
    SELECT *
    FROM {{ ref('int_faction_memberships_collapsed') }}
),

coalition_periods AS (
    SELECT *
    FROM {{ ref('int_coalition_periods') }}
),

coalition_per_faction AS (
    SELECT
        faction_id,
        COUNT(*) AS coalition_periods,
        STRING_AGG(DISTINCT CAST(government_num AS VARCHAR), ', ') AS coalition_governments
    FROM coalition_periods
    GROUP BY faction_id
),

members_per_faction AS (
    SELECT
        faction_id,
        COUNT(DISTINCT person_id) AS members
    FROM memberships
    GROUP BY faction_id
),

enhanced AS (
    SELECT
        CAST(factions.faction_id AS INTEGER) AS faction_id,
        CAST(factions.faction_name AS VARCHAR) AS faction_name,
        CAST(factions.knesset_num AS INTEGER) AS knesset_num,
        CAST(factions.start_at AS TIMESTAMP) AS start_at,
        CAST(factions.finish_at AS TIMESTAMP) AS finish_at,
        CAST(factions.is_current AS BOOLEAN) AS is_current,
        CAST(COALESCE(members_per_faction.members, 0) AS INTEGER) AS members,
        CAST(coalition_per_faction.faction_id IS NOT NULL AS BOOLEAN) AS was_in_coalition,
        CAST(coalition_per_faction.coalition_governments AS VARCHAR) AS coalition_governments
    FROM factions
    LEFT JOIN members_per_faction
        ON factions.faction_id = members_per_faction.faction_id
    LEFT JOIN coalition_per_faction
        ON factions.faction_id = coalition_per_faction.faction_id
)

SELECT *
FROM enhanced
