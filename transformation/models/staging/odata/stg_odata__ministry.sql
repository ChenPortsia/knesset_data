-- Government ministries | משרדי ממשלה
-- Grain: one row per ministry

select
    id                as ministry_id,
    trim(name)        as ministry_name,
    category_id,
    category_name,
    gov_id,
    is_active,
    last_updated_date as updated_at
from {{ current_rows('kns_gov_ministry') }}
