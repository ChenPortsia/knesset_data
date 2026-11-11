-- Parliamentary queries from MKs to ministers | שאילתות של חברי כנסת לשרים
-- Grain: one row per query (20th Knesset onward)

WITH queries AS (
    SELECT *
    FROM {{ ref('stg_odata__query') }}
),

statuses AS (
    SELECT *
    FROM {{ ref('stg_odata__status') }}
),

enhanced AS (
    SELECT
        CAST(queries.query_id AS INTEGER) AS query_id,
        CAST(queries.knesset_num AS INTEGER) AS knesset_num,
        CAST(queries.query_name AS VARCHAR) AS query_name,
        CAST(queries.query_type AS VARCHAR) AS query_type,
        CAST(statuses.status_name AS VARCHAR) AS status,
        CAST(queries.person_id AS INTEGER) AS person_id,
        CAST(queries.ministry_id AS INTEGER) AS ministry_id,
        CAST(CAST(queries.submitted_at AS DATE) AS DATE) AS submitted_date,
        CAST(CAST(queries.replied_at AS DATE) AS DATE) AS replied_date,
        CAST(DATE_DIFF('day', queries.submitted_at, queries.replied_at) AS INTEGER) AS reply_days,
        CAST(queries.replied_at IS NOT NULL AS BOOLEAN) AS is_replied
    FROM queries
    LEFT JOIN statuses
        ON queries.status_id = statuses.status_id
)

SELECT *
FROM enhanced
