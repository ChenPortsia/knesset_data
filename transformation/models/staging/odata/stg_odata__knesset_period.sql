-- Knesset terms split into assemblies and sittings | כנסות לפי כנסים ומושבים
-- Grain: one row per Knesset sitting period

select
    id                                as knesset_period_id,
    knesset_num,
    name                              as knesset_name,
    assembly,
    plenum,
    {{ local_time('plenum_start') }}  as start_at,
    {{ local_time('plenum_finish') }} as finish_at,
    is_current,
    last_updated_date                 as updated_at
from {{ source('odata', 'kns_knesset_dates') }}
