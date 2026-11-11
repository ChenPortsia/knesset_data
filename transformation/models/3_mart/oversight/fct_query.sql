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

memberships AS (
    SELECT *
    FROM {{ ref('int_faction_memberships_collapsed') }}
),

knesset_factions AS (
    SELECT *
    FROM {{ ref('int_person_knesset_factions') }}
),

coalition_periods AS (
    SELECT *
    FROM {{ ref('int_coalition_periods') }}
),

queries_dated AS (
    -- The asking MK's membership covering the submission date
    SELECT
        queries.query_id,
        memberships.faction_id
    FROM queries
    INNER JOIN memberships
        ON queries.person_id = memberships.person_id
        AND queries.submitted_at >= memberships.start_at
        AND queries.submitted_at < COALESCE(memberships.finish_at + INTERVAL 1 DAY, TIMESTAMP '9999-12-31')
    QUALIFY ROW_NUMBER() OVER (PARTITION BY queries.query_id ORDER BY memberships.start_at DESC) = 1
),

query_factions AS (
    -- Dated membership first; else the MK's only faction in that Knesset (as for votes)
    SELECT
        queries.query_id,
        queries.submitted_at,
        COALESCE(queries_dated.faction_id, knesset_factions.faction_id) AS faction_id
    FROM queries
    LEFT JOIN queries_dated
        ON queries.query_id = queries_dated.query_id
    LEFT JOIN knesset_factions
        ON queries.person_id = knesset_factions.person_id
        AND queries.knesset_num = knesset_factions.knesset_num
),

queries_in_coalition AS (
    SELECT DISTINCT query_factions.query_id
    FROM query_factions
    INNER JOIN coalition_periods
        ON query_factions.faction_id = coalition_periods.faction_id
        AND query_factions.submitted_at >= coalition_periods.start_at
        AND query_factions.submitted_at < COALESCE(coalition_periods.finish_at + INTERVAL 1 DAY, TIMESTAMP '9999-12-31')
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
        CAST(queries.replied_at IS NOT NULL AS BOOLEAN) AS is_replied,
        CAST(
            CASE
                WHEN queries_in_coalition.query_id IS NOT NULL THEN 'coalition'
                WHEN query_factions.faction_id IS NOT NULL THEN 'opposition'
            END AS VARCHAR
        ) AS asker_camp
    FROM queries
    LEFT JOIN statuses
        ON queries.status_id = statuses.status_id
    LEFT JOIN query_factions
        ON queries.query_id = query_factions.query_id
    LEFT JOIN queries_in_coalition
        ON queries.query_id = queries_in_coalition.query_id
)

SELECT *
FROM enhanced
