-- Motions for the agenda | הצעות לסדר היום
-- Grain: one row per motion

WITH source AS (
    SELECT *
    FROM {{ source('odata', 'kns_agenda') }}
),

renamed AS (
    SELECT
        CAST(id AS INTEGER)                                            AS agenda_id,
        CAST(knesset_num AS INTEGER)                                   AS knesset_num,
        CAST(number AS INTEGER)                                        AS agenda_number,
        CAST(TRIM(name) AS VARCHAR)                                    AS agenda_name,
        CAST(classification_id AS INTEGER)                             AS classification_id,
        CAST(classification_desc AS VARCHAR)                           AS classification,
        CAST(sub_type_id AS INTEGER)                                   AS sub_type_id,
        CAST(sub_type_desc AS VARCHAR)                                 AS sub_type,
        CAST(status_id AS INTEGER)                                     AS status_id,
        CAST(initiator_person_id AS INTEGER)                           AS initiator_person_id,
        CAST(minister_person_id AS INTEGER)                            AS minister_person_id,
        CAST(committee_id AS INTEGER)                                  AS committee_id,
        CAST(recommend_committee_id AS INTEGER)                        AS recommended_committee_id,
        CAST(leading_agenda_id AS INTEGER)                             AS leading_agenda_id,
        CAST(gov_recommendation_id AS INTEGER)                         AS gov_recommendation_id,
        CAST(gov_recommendation_desc AS VARCHAR)                       AS gov_recommendation,
        CAST(postopenment_reason_id AS INTEGER)                        AS postponement_reason_id,
        CAST(postopenment_reason_desc AS VARCHAR)                      AS postponement_reason,
        CAST({{ local_time('president_decision_date') }} AS TIMESTAMP) AS president_decision_at,
        CAST(last_updated_date AS TIMESTAMPTZ)                         AS updated_at,
        CAST(_dlt_valid_from AS TIMESTAMPTZ)                           AS loaded_at,
        CAST(_dlt_valid_to AS TIMESTAMPTZ)                             AS valid_to
    FROM source
),

filtered AS (
    SELECT *
    FROM renamed
    WHERE {{ is_current('kns_agenda', 'agenda_id') }}
),

enhanced AS (
    SELECT
        *
    FROM filtered
)

SELECT * EXCLUDE (valid_to)
FROM enhanced
