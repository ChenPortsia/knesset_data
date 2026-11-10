-- Plenum votes (one per vote held) | הצבעות במליאה
-- Grain: one row per vote

select
    id                                 as vote_id,
    session_id                         as plenum_session_id,
    item_id,
    ordinal,
    {{ local_time('vote_date_time') }} as voted_at,
    vote_title,
    vote_subject,
    vote_method_id,
    vote_method_desc                   as vote_method,
    vote_status_code                   as vote_status_id,
    vote_status_desc                   as vote_status,
    is_no_confidence_in_gov            as is_no_confidence,
    for_option_id,
    for_option_desc                    as for_option,
    against_option_id,
    against_option_desc                as against_option,
    last_updated_date                  as updated_at
from {{ current_rows('kns_plenum_vote') }}
