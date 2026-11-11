-- Plenum sessions | ישיבות מליאה
-- Grain: one row per plenum session (20th Knesset onward)

WITH plenum_sessions AS (
    SELECT *
    FROM {{ ref('stg_odata__plenum_session') }}
),

votes AS (
    SELECT *
    FROM {{ ref('int_votes_joined_to_items') }}
),

votes_per_session AS (
    SELECT
        plenum_session_id,
        COUNT(*) AS votes
    FROM votes
    GROUP BY plenum_session_id
),

enhanced AS (
    SELECT
        CAST(plenum_sessions.plenum_session_id AS INTEGER) AS plenum_session_id,
        CAST(plenum_sessions.knesset_num AS INTEGER) AS knesset_num,
        CAST(CAST(plenum_sessions.start_at AS DATE) AS DATE) AS session_date,
        CAST(plenum_sessions.start_at AS TIMESTAMP) AS start_at,
        CAST(plenum_sessions.finish_at AS TIMESTAMP) AS finish_at,
        CAST(plenum_sessions.session_number AS INTEGER) AS session_number,
        CAST(plenum_sessions.session_name AS VARCHAR) AS session_name,
        CAST(plenum_sessions.is_special_meeting AS BOOLEAN) AS is_special_meeting,
        CAST(COALESCE(votes_per_session.votes, 0) AS INTEGER) AS votes
    FROM plenum_sessions
    LEFT JOIN votes_per_session
        ON plenum_sessions.plenum_session_id = votes_per_session.plenum_session_id
)

SELECT *
FROM enhanced
