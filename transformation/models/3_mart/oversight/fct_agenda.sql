-- Motions for the agenda | הצעות לסדר היום
-- Grain: one row per motion (20th Knesset onward)

WITH motions AS (
    SELECT *
    FROM {{ ref('stg_odata__agenda') }}
),

statuses AS (
    SELECT *
    FROM {{ ref('stg_odata__status') }}
),

enhanced AS (
    SELECT
        CAST(motions.agenda_id AS INTEGER) AS agenda_id,
        CAST(motions.knesset_num AS INTEGER) AS knesset_num,
        CAST(motions.agenda_name AS VARCHAR) AS agenda_name,
        CAST(motions.classification AS VARCHAR) AS classification,
        CAST(motions.sub_type AS VARCHAR) AS sub_type,
        CAST(statuses.status_name AS VARCHAR) AS status,
        CAST(motions.initiator_person_id AS INTEGER) AS initiator_person_id,
        CAST(motions.minister_person_id AS INTEGER) AS minister_person_id,
        CAST(motions.committee_id AS INTEGER) AS committee_id,
        CAST(motions.gov_recommendation AS VARCHAR) AS gov_recommendation,
        CAST(CAST(motions.president_decision_at AS DATE) AS DATE) AS decision_date
    FROM motions
    LEFT JOIN statuses
        ON motions.status_id = statuses.status_id
)

SELECT *
FROM enhanced
