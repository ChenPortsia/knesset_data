-- Who held which position, when: MK in a faction, minister, committee member | מי כיהן באיזה תפקיד ומתי: ח"כ בסיעה, שר, חבר ועדה
-- Grain: one row per person, position and period

select
    id                              as person_position_id,
    person_id,
    position_id,
    knesset_num,
    faction_id,
    faction_name,
    committee_id,
    committee_name,
    gov_ministry_id                 as ministry_id,
    gov_ministry_name               as ministry_name,
    government_num,
    duty_desc                       as duty,
    {{ local_time('start_date') }}  as start_at,
    {{ local_time('finish_date') }} as finish_at,
    is_current,
    last_updated_date               as updated_at
from {{ source('odata', 'kns_person_to_position') }}
