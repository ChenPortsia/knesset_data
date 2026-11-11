-- MK faction memberships over time | חברות ח"כים בסיעות לאורך זמן
-- Grain: one row per person, faction and continuous membership period

WITH memberships AS (
    SELECT *
    FROM {{ ref('int_faction_memberships_collapsed') }}
),

enhanced AS (
    SELECT
        CAST(membership_id AS VARCHAR) AS membership_id,
        CAST(person_id AS INTEGER) AS person_id,
        CAST(faction_id AS INTEGER) AS faction_id,
        CAST(knesset_num AS INTEGER) AS knesset_num,
        CAST(start_at AS TIMESTAMP) AS start_at,
        CAST(finish_at AS TIMESTAMP) AS finish_at,
        CAST(CAST(start_at AS DATE) AS DATE) AS start_date,
        CAST(CAST(finish_at AS DATE) AS DATE) AS finish_date,
        CAST(is_current AS BOOLEAN) AS is_current
    FROM memberships
)

SELECT *
FROM enhanced
