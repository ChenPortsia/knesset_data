-- Types of items discussed in sessions | סוגי פריטים הנדונים בישיבות
-- Grain: one row per item type

select
    id         as item_type_id,
    "desc"     as item_type_name,
    table_name as source_table
from {{ source('odata', 'kns_item_type') }}
