-- Committee sessions (meetings) | ישיבות ועדה
-- Grain: one row per committee session

select
    id                              as committee_session_id,
    committee_id,
    knesset_num,
    number                          as session_number,
    type_id                         as session_type_id,
    type_desc                       as session_type,
    status_id,
    status_desc                     as status,
    location,
    session_url,
    broadcast_url,
    note,
    {{ local_time('start_date') }}  as start_at,
    {{ local_time('finish_date') }} as finish_at,
    last_updated_date               as updated_at
from {{ source('odata', 'kns_committee_session') }}
