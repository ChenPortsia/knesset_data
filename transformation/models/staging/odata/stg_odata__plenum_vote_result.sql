-- How each MK voted in each plenum vote | איך הצביע כל ח"כ בכל הצבעה במליאה
-- Grain: one row per vote and MK

select
    id                                             as vote_result_id,
    vote_id,
    mk_id                                          as person_id,
    session_id                                     as plenum_session_id,
    item_id,
    {{ local_time('vote_date') }}                  as voted_at,
    result_code,
    {{ code_label('vote_result', 'result_code') }} as result,
    result_desc                                    as result_he,
    last_updated_date                              as updated_at
from {{ source('odata', 'kns_plenum_vote_result') }}
