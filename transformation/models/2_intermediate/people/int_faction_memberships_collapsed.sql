-- MK faction memberships over time, with overlapping periods merged | חברות ח"כים בסיעות לאורך זמן
-- Grain: one row per person, faction and continuous membership period
-- Source rows: positions "faction member" (54) and "faction chair" (48). A chair usually
-- also has a member row for the same time, so overlapping periods are merged (gaps and islands).

WITH person_positions AS (
    SELECT *
    FROM {{ ref('stg_odata__person_position') }}
),

factions AS (
    SELECT *
    FROM {{ ref('stg_odata__faction') }}
),

filtered AS (
    SELECT
        person_id,
        faction_id,
        start_at,
        COALESCE(finish_at, TIMESTAMP '9999-12-31') AS finish_at  -- open-ended: still a member
    FROM person_positions
    WHERE position_id IN (48, 54)
      AND faction_id IS NOT NULL
      AND start_at IS NOT NULL
),

periods_flagged AS (
    -- A period starts a new island unless it begins before an earlier period has ended
    SELECT
        *,
        MAX(finish_at) OVER (
            PARTITION BY person_id, faction_id
            ORDER BY start_at, finish_at
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ) AS previous_finish_at
    FROM filtered
),

periods_numbered AS (
    SELECT
        *,
        SUM(CASE WHEN previous_finish_at >= start_at THEN 0 ELSE 1 END) OVER (
            PARTITION BY person_id, faction_id
            ORDER BY start_at, finish_at
        ) AS period_number
    FROM periods_flagged
),

periods_collapsed AS (
    SELECT
        person_id,
        faction_id,
        MIN(start_at) AS start_at,
        MAX(finish_at) AS finish_at
    FROM periods_numbered
    GROUP BY person_id, faction_id, period_number
),

enhanced AS (
    SELECT
        CAST(MD5(CONCAT_WS('|', periods_collapsed.person_id, periods_collapsed.faction_id, periods_collapsed.start_at)) AS VARCHAR) AS membership_id,
        CAST(periods_collapsed.person_id AS INTEGER) AS person_id,
        CAST(periods_collapsed.faction_id AS INTEGER) AS faction_id,
        CAST(factions.faction_name AS VARCHAR) AS faction_name,
        CAST(factions.knesset_num AS INTEGER) AS knesset_num,
        CAST(periods_collapsed.start_at AS TIMESTAMP) AS start_at,
        CAST(NULLIF(periods_collapsed.finish_at, TIMESTAMP '9999-12-31') AS TIMESTAMP) AS finish_at,
        CAST(periods_collapsed.finish_at = TIMESTAMP '9999-12-31' AS BOOLEAN) AS is_current
    FROM periods_collapsed
    LEFT JOIN factions
        ON periods_collapsed.faction_id = factions.faction_id
)

SELECT *
FROM enhanced
