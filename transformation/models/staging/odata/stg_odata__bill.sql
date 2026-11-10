-- Bills (proposed laws) | הצעות חוק
-- Grain: one row per bill

select
    id                                             as bill_id,
    knesset_num,
    trim(name)                                     as bill_name,
    type_id                                        as bill_type_id,
    type_desc                                      as bill_type,
    {{ code_label('bill_origin', 'sub_type_id') }} as origin,
    sub_type_desc                                  as origin_he,
    private_number,
    number                                         as bill_number,
    committee_id,
    status_id,
    postponement_reason_id,
    postponement_reason_desc                       as postponement_reason,
    is_continuation_bill,
    {{ local_time('publication_date') }}           as published_at,
    publication_series_id,
    publication_series_desc                        as publication_series,
    publication_series_first_call_id               as first_call_series_id,
    publication_series_first_call_desc             as first_call_series,
    magazine_number,
    page_number,
    summary_law                                    as summary,
    last_updated_date                              as updated_at
from {{ current_rows('kns_bill') }}
