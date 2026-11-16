-- Each session's speakers linked to people | קישור הדוברים בכל ישיבה לאנשים
-- Grain: one row per committee session and speaker
-- A name is matched only against people who held a post or sat in a faction in that Knesset,
-- and only for speakers the protocol marks as MKs (a chair title or a faction in brackets).
-- Rules, in order: the same name; the same first and last word (a middle name dropped);
-- a close spelling. The protocol's speaker ids are not used: carrying a link by id was
-- tried and linked different people (the ids repeat across sessions only most of the time).

-- A table, not a view: the name matching is the heavy part and fct_turn reads it twice
{{ config(materialized='table') }}

WITH speakers AS (
    SELECT *
    FROM {{ ref('stg_protocols__speakers') }}
),

committee_sessions AS (
    SELECT *
    FROM {{ ref('stg_odata__committee_session') }}
),

persons AS (
    SELECT *
    FROM {{ ref('stg_odata__person') }}
),

memberships AS (
    SELECT *
    FROM {{ ref('int_faction_memberships_collapsed') }}
),

roles AS (
    SELECT *
    FROM {{ ref('int_person_roles_classified') }}
),

serving AS (
    -- Who could be speaking as an MK or minister in each Knesset
    SELECT person_id, knesset_num FROM memberships
    UNION
    SELECT person_id, knesset_num FROM roles
),

candidates AS (
    SELECT
        serving.knesset_num,
        serving.person_id,
        {{ name_key('persons.full_name') }} AS name_key
    FROM serving
    INNER JOIN persons
        ON serving.person_id = persons.person_id
),

candidate_names AS (
    -- Names that mean one person in a Knesset; a name two people share links to nobody
    SELECT
        knesset_num,
        name_key,
        SPLIT_PART(name_key, ' ', 1) AS first_word,
        SPLIT_PART(name_key, ' ', -1) AS last_word,
        ANY_VALUE(person_id) AS person_id
    FROM candidates
    GROUP BY knesset_num, name_key
    HAVING COUNT(DISTINCT person_id) = 1
),

named AS (
    SELECT
        speakers.*,
        committee_sessions.knesset_num,
        {{ name_key('speakers.person_name') }} AS name_key,
        speakers.is_chair OR speakers.faction_text IS NOT NULL AS is_marked_mk
    FROM speakers
    INNER JOIN committee_sessions
        ON speakers.committee_session_id = committee_sessions.committee_session_id
),

same_name AS (
    SELECT
        named.committee_session_id,
        named.speaker_id,
        candidate_names.person_id
    FROM named
    INNER JOIN candidate_names
        ON named.knesset_num = candidate_names.knesset_num
        AND named.name_key = candidate_names.name_key
    WHERE named.is_marked_mk
),

first_and_last AS (
    SELECT
        named.committee_session_id,
        named.speaker_id,
        ANY_VALUE(candidate_names.person_id) AS person_id
    FROM named
    INNER JOIN candidate_names
        ON named.knesset_num = candidate_names.knesset_num
        AND SPLIT_PART(named.name_key, ' ', 1) = candidate_names.first_word
        AND SPLIT_PART(named.name_key, ' ', -1) = candidate_names.last_word
    WHERE named.is_marked_mk
      AND named.name_key LIKE '% %'
    GROUP BY named.committee_session_id, named.speaker_id
    HAVING COUNT(DISTINCT candidate_names.person_id) = 1
),

close_spelling AS (
    SELECT
        named.committee_session_id,
        named.speaker_id,
        ARG_MAX(candidate_names.person_id, JARO_WINKLER_SIMILARITY(named.name_key, candidate_names.name_key)) AS person_id
    FROM named
    INNER JOIN candidate_names
        ON named.knesset_num = candidate_names.knesset_num
        AND JARO_WINKLER_SIMILARITY(named.name_key, candidate_names.name_key) >= 0.92
    WHERE named.is_marked_mk
      AND LENGTH(named.name_key) <= 40
    GROUP BY named.committee_session_id, named.speaker_id
),

by_name AS (
    SELECT
        named.committee_session_id,
        named.speaker_id,
        COALESCE(same_name.person_id, first_and_last.person_id, close_spelling.person_id) AS person_id,
        CASE
            WHEN same_name.person_id IS NOT NULL THEN 'same_name'
            WHEN first_and_last.person_id IS NOT NULL THEN 'first_and_last_name'
            WHEN close_spelling.person_id IS NOT NULL THEN 'close_spelling'
        END AS link_method
    FROM named
    LEFT JOIN same_name
        ON named.committee_session_id = same_name.committee_session_id
        AND named.speaker_id = same_name.speaker_id
    LEFT JOIN first_and_last
        ON named.committee_session_id = first_and_last.committee_session_id
        AND named.speaker_id = first_and_last.speaker_id
    LEFT JOIN close_spelling
        ON named.committee_session_id = close_spelling.committee_session_id
        AND named.speaker_id = close_spelling.speaker_id
),

enhanced AS (
    SELECT
        CAST(named.committee_session_id AS INTEGER) AS committee_session_id,
        CAST(named.speaker_id AS INTEGER) AS speaker_id,
        CAST(named.knesset_num AS INTEGER) AS knesset_num,
        CAST(named.speaker_name AS VARCHAR) AS speaker_name,
        CAST(named.person_name AS VARCHAR) AS person_name,
        CAST(named.faction_text AS VARCHAR) AS faction_text,
        CAST(named.is_chair AS BOOLEAN) AS is_chair,
        CAST(named.is_marked_mk AS BOOLEAN) AS is_marked_mk,
        CAST(by_name.person_id AS INTEGER) AS person_id,
        CAST(by_name.link_method AS VARCHAR) AS link_method,
        CAST(
            CASE
                WHEN named.person_name IN ('קריאה', 'קריאות') THEN 'interjection'
                WHEN named.is_marked_mk THEN 'mk'
                ELSE 'other'
            END AS VARCHAR
        ) AS speaker_kind
    FROM named
    INNER JOIN by_name
        ON named.committee_session_id = by_name.committee_session_id
        AND named.speaker_id = by_name.speaker_id
)

SELECT *
FROM enhanced
