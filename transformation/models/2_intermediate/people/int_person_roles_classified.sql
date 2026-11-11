-- Who held which role, when: committee chairs and members, ministers, Speaker... | מי מילא איזה תפקיד ומתי
-- Grain: one row per person, role, committee or ministry, government and continuous period
-- Roles come from the position_roles seed. MK and faction-member rows are left out: faction
-- membership has its own model, and the source rewrote the 25th Knesset's MK rows.
-- Overlapping rows for the same role in the same Knesset are merged (the source repeats some,
-- with different end dates). A new Knesset starts a new period: the source re-issues posts
-- when a Knesset starts, and the post then belongs to the MK's new faction.

WITH person_positions AS (
    SELECT *
    FROM {{ ref('stg_odata__person_position') }}
),

position_roles AS (
    SELECT *
    FROM {{ ref('position_roles') }}
),

filtered AS (
    SELECT
        person_positions.person_id,
        position_roles.role,
        position_roles.role_group,
        person_positions.knesset_num,
        person_positions.committee_id,
        person_positions.ministry_id,
        person_positions.government_num,
        person_positions.start_at,
        COALESCE(person_positions.finish_at, TIMESTAMP '9999-12-31') AS finish_at
    FROM person_positions
    INNER JOIN position_roles
        ON person_positions.position_id = position_roles.position_id
    WHERE position_roles.role NOT IN ('mk', 'faction_member')
      AND person_positions.start_at IS NOT NULL
),

periods_flagged AS (
    SELECT
        *,
        MAX(finish_at) OVER (
            PARTITION BY person_id, role, committee_id, ministry_id, government_num, knesset_num
            ORDER BY start_at, finish_at
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ) AS previous_finish_at
    FROM filtered
),

periods_numbered AS (
    SELECT
        *,
        SUM(CASE WHEN previous_finish_at >= start_at THEN 0 ELSE 1 END) OVER (
            PARTITION BY person_id, role, committee_id, ministry_id, government_num, knesset_num
            ORDER BY start_at, finish_at
        ) AS period_number
    FROM periods_flagged
),

periods_collapsed AS (
    SELECT
        person_id,
        role,
        role_group,
        committee_id,
        ministry_id,
        government_num,
        knesset_num,
        MIN(start_at) AS start_at,
        MAX(finish_at) AS finish_at
    FROM periods_numbered
    GROUP BY person_id, role, role_group, committee_id, ministry_id, government_num, knesset_num, period_number
),

enhanced AS (
    SELECT
        CAST(MD5(CONCAT_WS('|', person_id, role, committee_id, ministry_id, government_num, knesset_num, start_at)) AS VARCHAR) AS person_role_id,
        CAST(person_id AS INTEGER) AS person_id,
        CAST(role AS VARCHAR) AS role,
        CAST(role_group AS VARCHAR) AS role_group,
        CAST(knesset_num AS INTEGER) AS knesset_num,
        CAST(committee_id AS INTEGER) AS committee_id,
        CAST(ministry_id AS INTEGER) AS ministry_id,
        CAST(government_num AS INTEGER) AS government_num,
        CAST(start_at AS TIMESTAMP) AS start_at,
        CAST(NULLIF(finish_at, TIMESTAMP '9999-12-31') AS TIMESTAMP) AS finish_at
    FROM periods_collapsed
)

SELECT *
FROM enhanced
