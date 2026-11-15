-- J11: How do the Knessets since the 20th compare on bills, laws, votes, committee sessions
-- and queries?

WITH knessets AS (
    SELECT *
    FROM {{ ref('dim_knesset') }}
),

bills AS (
    SELECT
        knesset_num,
        COUNT(*) AS bills,
        COUNT(*) FILTER (WHERE is_passed) AS laws_passed
    FROM {{ ref('dim_bill') }}
    GROUP BY knesset_num
),

plenum_votes AS (
    SELECT
        knesset_num,
        COUNT(*) AS plenum_votes
    FROM {{ ref('fct_plenum_vote') }}
    GROUP BY knesset_num
),

committee_sessions AS (
    SELECT
        knesset_num,
        COUNT(*) AS committee_sessions
    FROM {{ ref('fct_committee_session') }}
    WHERE status <> 'מבוטלת'
    GROUP BY knesset_num
),

queries AS (
    SELECT
        knesset_num,
        COUNT(*) AS queries
    FROM {{ ref('fct_query') }}
    GROUP BY knesset_num
),

filtered AS (
    SELECT *
    FROM knessets
    WHERE is_in_scope
),

enhanced AS (
    SELECT
        filtered.knesset_num,
        CAST(filtered.start_at AS DATE) AS start_date,
        CAST(filtered.finish_at AS DATE) AS finish_date,
        COALESCE(bills.bills, 0) AS bills,
        COALESCE(bills.laws_passed, 0) AS laws_passed,
        COALESCE(plenum_votes.plenum_votes, 0) AS plenum_votes,
        COALESCE(committee_sessions.committee_sessions, 0) AS committee_sessions,
        COALESCE(queries.queries, 0) AS queries
    FROM filtered
    LEFT JOIN bills
        ON filtered.knesset_num = bills.knesset_num
    LEFT JOIN plenum_votes
        ON filtered.knesset_num = plenum_votes.knesset_num
    LEFT JOIN committee_sessions
        ON filtered.knesset_num = committee_sessions.knesset_num
    LEFT JOIN queries
        ON filtered.knesset_num = queries.knesset_num
)

SELECT *
FROM enhanced
ORDER BY knesset_num
