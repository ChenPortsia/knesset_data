-- Calendar: one row per day, with the Knesset sitting on that day | לוח שנה: שורה לכל יום
-- Grain: one row per day, 2015-01-01 to 2030-12-31

WITH date_spine AS (
    SELECT CAST(range AS DATE) AS date_day
    FROM RANGE(DATE '2015-01-01', DATE '2031-01-01', INTERVAL 1 DAY)
),

knessets AS (
    SELECT *
    FROM {{ ref('dim_knesset') }}
),

enhanced AS (
    SELECT
        CAST(date_spine.date_day AS DATE) AS date_day,
        CAST(YEAR(date_spine.date_day) AS INTEGER) AS year,
        CAST(QUARTER(date_spine.date_day) AS INTEGER) AS quarter,
        CAST(MONTH(date_spine.date_day) AS INTEGER) AS month,
        CAST(STRFTIME(date_spine.date_day, '%Y-%m') AS VARCHAR) AS year_month,
        CAST(STRFTIME(date_spine.date_day, '%B') AS VARCHAR) AS month_name,
        CAST(DATE_TRUNC('week', date_spine.date_day) AS DATE) AS week_start,
        CAST(ISODOW(date_spine.date_day) AS INTEGER) AS day_of_week,
        CAST(STRFTIME(date_spine.date_day, '%A') AS VARCHAR) AS day_name,
        CAST(ISODOW(date_spine.date_day) IN (5, 6) AS BOOLEAN) AS is_weekend,  -- Friday, Saturday
        CAST(knessets.knesset_num AS INTEGER) AS knesset_num
    FROM date_spine
    LEFT JOIN knessets
        ON date_spine.date_day >= CAST(knessets.start_at AS DATE)
        AND date_spine.date_day < COALESCE(CAST(knessets.finish_at AS DATE), DATE '9999-12-31')
)

SELECT *
FROM enhanced
