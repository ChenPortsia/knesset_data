-- Items on a committee session agenda (bills, queries, topics); all Knessets | פריטים בסדר היום של ישיבת ועדה; כל הכנסות
-- Grain: one row per item per committee session

select
    id                   as session_item_id,
    committee_session_id,
    item_id,
    item_type_id,
    name                 as item_name,
    ordinal,
    status_id,
    last_updated_date    as updated_at
from {{ source('odata', 'kns_cmt_session_item') }}
