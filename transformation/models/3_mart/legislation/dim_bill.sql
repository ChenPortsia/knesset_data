-- Bills, with their stage, outcome, initiators and activity | הצעות חוק עם שלב, תוצאה, יוזמים ופעילות
-- Grain: one row per bill (20th Knesset onward)

WITH bills AS (
    SELECT *
    FROM {{ ref('int_bills_joined_to_stages') }}
),

committees AS (
    SELECT *
    FROM {{ ref('stg_odata__committee') }}
),

bill_initiators AS (
    SELECT *
    FROM {{ ref('int_bill_initiators_filtered') }}
),

session_bills AS (
    SELECT *
    FROM {{ ref('int_committee_sessions_bridged_to_bills') }}
),

votes AS (
    SELECT *
    FROM {{ ref('int_votes_joined_to_items') }}
),

initiators_per_bill AS (
    SELECT
        bill_id,
        COUNT(*) FILTER (WHERE is_initiator) AS initiators,
        COUNT(*) FILTER (WHERE NOT is_initiator) AS joiners,
        MIN(person_id) FILTER (WHERE is_first_initiator) AS first_initiator_person_id
    FROM bill_initiators
    GROUP BY bill_id
),

committee_sessions_per_bill AS (
    SELECT
        bill_id,
        COUNT(*) AS committee_sessions,
        MIN(session_start_at) AS first_committee_session_at
    FROM session_bills
    GROUP BY bill_id
),

votes_per_bill AS (
    SELECT
        bill_id,
        COUNT(*) AS plenum_votes,
        MAX(voted_at) AS last_voted_at
    FROM votes
    WHERE bill_id IS NOT NULL
    GROUP BY bill_id
),

enhanced AS (
    SELECT
        CAST(bills.bill_id AS INTEGER) AS bill_id,
        CAST(bills.bill_name AS VARCHAR) AS bill_name,
        CAST(bills.knesset_num AS INTEGER) AS knesset_num,
        CAST(bills.origin AS VARCHAR) AS origin,
        CAST(bills.status_id AS INTEGER) AS status_id,
        CAST(bills.status_he AS VARCHAR) AS status_he,
        CAST(bills.status_en AS VARCHAR) AS status_en,
        CAST(bills.stage AS VARCHAR) AS stage,
        CAST(bills.stage_order AS INTEGER) AS stage_order,
        CAST(bills.outcome AS VARCHAR) AS outcome,
        CAST(bills.is_passed AS BOOLEAN) AS is_passed,
        CAST(bills.committee_id AS INTEGER) AS committee_id,
        CAST(committees.committee_name AS VARCHAR) AS committee_name,
        CAST(initiators_per_bill.first_initiator_person_id AS INTEGER) AS first_initiator_person_id,
        CAST(COALESCE(initiators_per_bill.initiators, 0) AS INTEGER) AS initiators,
        CAST(COALESCE(initiators_per_bill.joiners, 0) AS INTEGER) AS joiners,
        CAST(COALESCE(committee_sessions_per_bill.committee_sessions, 0) AS INTEGER) AS committee_sessions,
        CAST(committee_sessions_per_bill.first_committee_session_at AS TIMESTAMP) AS first_committee_session_at,
        CAST(COALESCE(votes_per_bill.plenum_votes, 0) AS INTEGER) AS plenum_votes,
        CAST(votes_per_bill.last_voted_at AS TIMESTAMP) AS last_voted_at,
        CAST(bills.published_at AS TIMESTAMP) AS published_at,
        CAST(bills.is_continuation_bill AS BOOLEAN) AS is_continuation_bill
    FROM bills
    LEFT JOIN committees
        ON bills.committee_id = committees.committee_id
    LEFT JOIN initiators_per_bill
        ON bills.bill_id = initiators_per_bill.bill_id
    LEFT JOIN committee_sessions_per_bill
        ON bills.bill_id = committee_sessions_per_bill.bill_id
    LEFT JOIN votes_per_bill
        ON bills.bill_id = votes_per_bill.bill_id
)

SELECT *
FROM enhanced
