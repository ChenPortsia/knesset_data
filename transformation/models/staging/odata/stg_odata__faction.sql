-- Factions (parliamentary groups) per Knesset | סיעות בכל כנסת
-- Grain: one row per faction per Knesset

select
    id                              as faction_id,
    trim(name)                      as faction_name,
    knesset_num,
    {{ local_time('start_date') }}  as start_at,
    {{ local_time('finish_date') }} as finish_at,
    is_current,
    last_updated_date               as updated_at
from {{ current_rows('kns_faction') }}
