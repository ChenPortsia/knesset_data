-- Israeli laws in force or repealed; all Knessets | חוקי מדינת ישראל; כל הכנסות
-- Grain: one row per law

select
    id                                          as law_id,
    knesset_num,
    trim(name)                                  as law_name,
    is_basic_law,
    is_favorite_law,
    is_budget_law,
    law_validity_id                             as validity_id,
    law_validity_desc                           as validity,
    {{ local_time('publication_date') }}        as published_at,
    {{ local_time('latest_publication_date') }} as latest_published_at,
    {{ local_time('validity_start_date') }}     as valid_from,
    validity_start_date_notes                   as valid_from_notes,
    {{ local_time('validity_finish_date') }}    as valid_until,
    validity_finish_date_notes                  as valid_until_notes,
    last_updated_date                           as updated_at
from {{ current_rows('kns_israel_law') }}
