-- Status codes for bills, queries, sessions and more | קודי סטטוס להצעות חוק, שאילתות, ישיבות ועוד
-- Grain: one row per status

select
    id                as status_id,
    "desc"            as status_name,
    type_id           as status_type_id,
    type_desc         as status_type,
    order_transition,
    is_active,
    last_updated_date as updated_at
from {{ source('odata', 'kns_status') }}
