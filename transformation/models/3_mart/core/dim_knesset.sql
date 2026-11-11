-- Knesset terms | כנסות
-- Grain: one row per Knesset

WITH knesset_periods AS (
    SELECT *
    FROM {{ ref('stg_odata__knesset_period') }}
),

knessets AS (
    -- Periods are assemblies and sittings; one row per Knesset
    SELECT
        knesset_num,
        MIN(knesset_name) AS knesset_name,
        MIN(start_at) AS start_at,
        CASE WHEN BOOL_OR(is_current) THEN NULL ELSE MAX(finish_at) END AS finish_at,
        BOOL_OR(is_current) AS is_current
    FROM knesset_periods
    GROUP BY knesset_num
),

enhanced AS (
    SELECT
        CAST(knesset_num AS INTEGER) AS knesset_num,
        CAST(knesset_name AS VARCHAR) AS knesset_name,
        CAST(start_at AS TIMESTAMP) AS start_at,
        CAST(finish_at AS TIMESTAMP) AS finish_at,
        CAST(is_current AS BOOLEAN) AS is_current,
        CAST(knesset_num >= {{ var('from_knesset') }} AS BOOLEAN) AS is_in_scope
    FROM knessets
)

SELECT *
FROM enhanced
