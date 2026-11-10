-- Knesset committees per Knesset | ועדות הכנסת בכל כנסת
-- Grain: one row per committee per Knesset

select
    id                              as committee_id,
    trim(name)                      as committee_name,
    knesset_num,
    category_id,
    category_desc                   as category_name,
    committee_type_id,
    committee_type_desc             as committee_type,
    additional_type_id,
    additional_type_desc            as additional_type,
    parent_committee_id,
    committee_parent_name           as parent_committee_name,
    {{ local_time('start_date') }}  as start_at,
    {{ local_time('finish_date') }} as finish_at,
    is_current,
    last_updated_date               as updated_at
from {{ current_rows('kns_committee') }}
