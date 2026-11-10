-- Motions for the agenda | הצעות לסדר היום
-- Grain: one row per motion

select
    id                                          as agenda_id,
    knesset_num,
    number                                      as agenda_number,
    trim(name)                                  as agenda_name,
    classification_id,
    classification_desc                         as classification,
    sub_type_id,
    sub_type_desc                               as sub_type,
    status_id,
    initiator_person_id,
    minister_person_id,
    committee_id,
    recommend_committee_id                      as recommended_committee_id,
    leading_agenda_id,
    gov_recommendation_id,
    gov_recommendation_desc                     as gov_recommendation,
    postopenment_reason_id                      as postponement_reason_id,
    postopenment_reason_desc                    as postponement_reason,
    {{ local_time('president_decision_date') }} as president_decision_at,
    last_updated_date                           as updated_at
from {{ current_rows('kns_agenda') }}
