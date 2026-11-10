-- Items on a plenum session agenda; all Knessets | פריטים בסדר היום של ישיבת מליאה; כל הכנסות
-- Grain: one row per item per plenum session

select
    id                as session_item_id,
    plenum_session_id,
    item_id,
    item_type_id,
    item_type_desc    as item_type,
    name              as item_name,
    ordinal,
    status_id,
    is_discussion = 1 as is_discussion,
    last_updated_date as updated_at
from {{ source('odata', 'kns_plm_session_item') }}
