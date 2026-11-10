-- Position types (MK, minister, committee chair...) | סוגי תפקידים (ח"כ, שר, יו"ר ועדה...)
-- Grain: one row per position type

select
    id                as position_id,
    description       as position_name,
    gender_id,
    last_updated_date as updated_at
from {{ current_rows('kns_position') }}
