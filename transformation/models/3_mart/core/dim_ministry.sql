-- Government ministries | משרדי ממשלה
-- Grain: one row per ministry

WITH ministries AS (
    SELECT *
    FROM {{ ref('stg_odata__ministry') }}
),

enhanced AS (
    SELECT
        CAST(ministry_id AS INTEGER) AS ministry_id,
        CAST(ministry_name AS VARCHAR) AS ministry_name,
        CAST(category_name AS VARCHAR) AS category_name,
        CAST(is_active AS BOOLEAN) AS is_active
    FROM ministries
)

SELECT *
FROM enhanced
