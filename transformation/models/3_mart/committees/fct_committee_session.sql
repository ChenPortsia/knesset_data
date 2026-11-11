-- Committee sessions (meetings) | ישיבות ועדה
-- Grain: one row per committee session (20th Knesset onward)

WITH committee_sessions AS (
    SELECT *
    FROM {{ ref('stg_odata__committee_session') }}
),

session_bills AS (
    SELECT *
    FROM {{ ref('int_committee_sessions_bridged_to_bills') }}
),

bills_per_session AS (
    SELECT
        committee_session_id,
        COUNT(*) AS bills_discussed
    FROM session_bills
    GROUP BY committee_session_id
),

enhanced AS (
    SELECT
        CAST(committee_sessions.committee_session_id AS INTEGER) AS committee_session_id,
        CAST(committee_sessions.committee_id AS INTEGER) AS committee_id,
        CAST(committee_sessions.knesset_num AS INTEGER) AS knesset_num,
        CAST(CAST(committee_sessions.start_at AS DATE) AS DATE) AS session_date,
        CAST(committee_sessions.start_at AS TIMESTAMP) AS start_at,
        CAST(committee_sessions.finish_at AS TIMESTAMP) AS finish_at,
        CAST(DATE_DIFF('minute', committee_sessions.start_at, committee_sessions.finish_at) AS INTEGER) AS duration_minutes,
        CAST(committee_sessions.session_number AS INTEGER) AS session_number,
        CAST(committee_sessions.session_type AS VARCHAR) AS session_type,
        CAST(committee_sessions.status AS VARCHAR) AS status,
        CAST(COALESCE(bills_per_session.bills_discussed, 0) AS INTEGER) AS bills_discussed,
        CAST(committee_sessions.session_url AS VARCHAR) AS session_url
    FROM committee_sessions
    LEFT JOIN bills_per_session
        ON committee_sessions.committee_session_id = bills_per_session.committee_session_id
)

SELECT *
FROM enhanced
