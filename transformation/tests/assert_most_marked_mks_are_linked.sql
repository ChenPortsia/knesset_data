-- Milestone 4's bar: more than 90% of the speakers a protocol marks as MKs are linked to a
-- person. Fails if the share drops below that.
{{ config(enabled=target.name != 'sample') }}

SELECT
    COUNT(*) AS marked_mks,
    COUNT(person_id) AS linked
FROM {{ ref('int_speaker_links') }}
WHERE is_marked_mk
HAVING COUNT(person_id) < 0.9 * COUNT(*)
