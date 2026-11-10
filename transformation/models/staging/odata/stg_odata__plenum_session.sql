-- Plenum sessions | ישיבות מליאה
-- Grain: one row per plenum session

select
    id                              as plenum_session_id,
    knesset_num,
    number                          as session_number,
    name                            as session_name,
    is_special_meeting,
    {{ local_time('start_date') }}  as start_at,
    {{ local_time('finish_date') }} as finish_at,
    last_updated_date               as updated_at
from {{ current_rows('kns_plenum_session') }}
