-- When each faction was in the coalition, with known exceptions corrected | מתי כל סיעה הייתה בקואליציה, כולל תיקונים ידועים
-- Grain: one row per faction, government and continuous coalition period
-- The coalition_overrides seed replaces the derived periods of a faction in a government:
-- camp 'coalition' adds a period (a party in the coalition without government posts),
-- camp 'opposition' removes the derived ones (a faction that only lost an MK to the government).

WITH derived_periods AS (
    SELECT *
    FROM {{ ref('int_coalition_periods_derived') }}
),

overrides AS (
    SELECT *
    FROM {{ ref('coalition_overrides') }}
),

factions AS (
    SELECT *
    FROM {{ ref('stg_odata__faction') }}
),

filtered AS (
    -- Derived periods without an override for the same faction and government
    SELECT
        derived_periods.*,
        'government_posts' AS source
    FROM derived_periods
    LEFT JOIN overrides
        ON derived_periods.faction_id = overrides.faction_id
        AND derived_periods.government_num = overrides.government_num
    WHERE overrides.faction_id IS NULL
),

combined AS (
    SELECT faction_id, government_num, start_at, finish_at, source
    FROM filtered
    UNION ALL
    SELECT
        faction_id,
        government_num,
        CAST(start_date AS TIMESTAMP) AS start_at,
        CAST(finish_date AS TIMESTAMP) AS finish_at,
        'override' AS source
    FROM overrides
    WHERE camp = 'coalition'
),

enhanced AS (
    SELECT
        CAST(MD5(CONCAT_WS('|', combined.faction_id, combined.government_num, combined.start_at)) AS VARCHAR) AS coalition_period_id,
        CAST(combined.faction_id AS INTEGER) AS faction_id,
        CAST(factions.faction_name AS VARCHAR) AS faction_name,
        CAST(factions.knesset_num AS INTEGER) AS knesset_num,
        CAST(combined.government_num AS INTEGER) AS government_num,
        CAST(combined.start_at AS TIMESTAMP) AS start_at,
        CAST(combined.finish_at AS TIMESTAMP) AS finish_at,
        CAST(combined.source AS VARCHAR) AS source
    FROM combined
    LEFT JOIN factions
        ON combined.faction_id = factions.faction_id
)

SELECT *
FROM enhanced
