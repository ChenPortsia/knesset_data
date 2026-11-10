-- Parliamentary queries from MKs to ministers | שאילתות של חברי כנסת לשרים
-- Grain: one row per query

select
    id                                      as query_id,
    knesset_num,
    number                                  as query_number,
    trim(name)                              as query_name,
    type_id                                 as query_type_id,
    type_desc                               as query_type,
    status_id,
    person_id,
    gov_ministry_id                         as ministry_id,
    {{ local_time('submit_date') }}         as submitted_at,
    {{ local_time('reply_date_planned') }}  as reply_planned_at,
    {{ local_time('reply_minister_date') }} as replied_at,
    last_updated_date                       as updated_at
from {{ source('odata', 'kns_query') }}
