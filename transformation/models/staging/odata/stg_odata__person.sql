-- People: MKs, ministers and other office holders | אנשים: חברי כנסת, שרים ונושאי תפקידים
-- Grain: one row per person

select
    id                                         as person_id,
    trim(first_name)                           as first_name,
    trim(last_name)                            as last_name,
    trim(first_name) || ' ' || trim(last_name) as full_name,
    {{ code_label('gender', 'gender_id') }}    as gender,
    gender_desc                                as gender_he,
    email,
    is_current,
    last_updated_date                          as updated_at
from {{ current_rows('kns_person') }}
