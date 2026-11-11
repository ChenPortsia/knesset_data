-- When each faction was in the coalition, derived from government posts | מתי כל סיעה הייתה בקואליציה, לפי תפקידים בממשלה
-- Grain: one row per faction, government and continuous coalition period
-- Rule: a faction is in the coalition while at least one of its MKs holds a government post
-- (minister, deputy minister, prime minister). The minister's faction is the dated membership
-- covering the post's start, or else their only faction in that Knesset.
-- Known exceptions are corrected in int_coalition_periods with the coalition_overrides seed.

WITH roles AS (
    SELECT *
    FROM {{ ref('int_person_roles_classified') }}
),

memberships AS (
    SELECT *
    FROM {{ ref('int_faction_memberships_collapsed') }}
),

knesset_factions AS (
    SELECT *
    FROM {{ ref('int_person_knesset_factions') }}
),

filtered AS (
    SELECT *
    FROM roles
    WHERE role_group = 'government'
      AND government_num IS NOT NULL
),

posts_dated AS (
    -- The membership covering the start of the post
    SELECT
        filtered.person_role_id,
        memberships.faction_id
    FROM filtered
    INNER JOIN memberships
        ON filtered.person_id = memberships.person_id
        AND filtered.start_at >= memberships.start_at
        AND filtered.start_at < COALESCE(memberships.finish_at + INTERVAL 1 DAY, TIMESTAMP '9999-12-31')
    QUALIFY ROW_NUMBER() OVER (PARTITION BY filtered.person_role_id ORDER BY memberships.start_at DESC) = 1
),

posts_with_factions AS (
    SELECT
        filtered.government_num,
        COALESCE(posts_dated.faction_id, knesset_factions.faction_id) AS faction_id,
        filtered.start_at,
        COALESCE(filtered.finish_at, TIMESTAMP '9999-12-31') AS finish_at
    FROM filtered
    LEFT JOIN posts_dated
        ON filtered.person_role_id = posts_dated.person_role_id
    LEFT JOIN knesset_factions
        ON filtered.person_id = knesset_factions.person_id
        AND filtered.knesset_num = knesset_factions.knesset_num
),

periods_flagged AS (
    SELECT
        *,
        MAX(finish_at) OVER (
            PARTITION BY faction_id, government_num
            ORDER BY start_at, finish_at
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ) AS previous_finish_at
    FROM posts_with_factions
    WHERE faction_id IS NOT NULL  -- ministers who are not MKs have no faction
),

periods_numbered AS (
    SELECT
        *,
        SUM(CASE WHEN previous_finish_at >= start_at THEN 0 ELSE 1 END) OVER (
            PARTITION BY faction_id, government_num
            ORDER BY start_at, finish_at
        ) AS period_number
    FROM periods_flagged
),

enhanced AS (
    SELECT
        CAST(faction_id AS INTEGER) AS faction_id,
        CAST(government_num AS INTEGER) AS government_num,
        CAST(MIN(start_at) AS TIMESTAMP) AS start_at,
        CAST(NULLIF(MAX(finish_at), TIMESTAMP '9999-12-31') AS TIMESTAMP) AS finish_at
    FROM periods_numbered
    GROUP BY faction_id, government_num, period_number
)

SELECT *
FROM enhanced
