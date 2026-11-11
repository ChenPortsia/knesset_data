-- When each faction was in the coalition | מתי כל סיעה הייתה בקואליציה
-- Grain: one row per faction, government and continuous coalition period
-- Derived from government posts, with known exceptions from the coalition_overrides seed
-- (see int_coalition_periods). A faction outside every period was in opposition.

WITH coalition_periods AS (
    SELECT *
    FROM {{ ref('int_coalition_periods') }}
),

enhanced AS (
    SELECT
        CAST(coalition_period_id AS VARCHAR) AS coalition_period_id,
        CAST(faction_id AS INTEGER) AS faction_id,
        CAST(faction_name AS VARCHAR) AS faction_name,
        CAST(knesset_num AS INTEGER) AS knesset_num,
        CAST(government_num AS INTEGER) AS government_num,
        CAST(CAST(start_at AS DATE) AS DATE) AS start_date,
        CAST(CAST(finish_at AS DATE) AS DATE) AS finish_date,
        CAST(source AS VARCHAR) AS source
    FROM coalition_periods
)

SELECT *
FROM enhanced
