-- MKs who initiated or joined a bill; all Knessets | חברי כנסת שיזמו או הצטרפו להצעת חוק; כל הכנסות
-- Grain: one row per bill and person

select
    id                as bill_initiator_id,
    bill_id,
    person_id,
    is_initiator,
    ordinal,
    last_updated_date as updated_at
from {{ current_rows('kns_bill_initiator') }}
