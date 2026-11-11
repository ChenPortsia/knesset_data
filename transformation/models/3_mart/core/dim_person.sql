-- People: MKs, ministers and other office holders | אנשים: חברי כנסת, שרים ונושאי תפקידים
-- Grain: one row per person

WITH persons AS (
    SELECT *
    FROM {{ ref('stg_odata__person') }}
),

person_positions AS (
    SELECT *
    FROM {{ ref('stg_odata__person_position') }}
),

memberships AS (
    SELECT *
    FROM {{ ref('int_faction_memberships_collapsed') }}
),

mk_terms AS (
    -- MK positions (43 male, 61 female form) in the Knessets we load
    SELECT
        person_id,
        MIN(knesset_num) AS first_knesset_num,
        MAX(knesset_num) AS last_knesset_num,
        COUNT(DISTINCT knesset_num) AS knessets_served
    FROM person_positions
    WHERE position_id IN (43, 61)
      AND knesset_num IS NOT NULL
    GROUP BY person_id
),

latest_memberships AS (
    SELECT
        person_id,
        faction_id,
        faction_name
    FROM memberships
    QUALIFY ROW_NUMBER() OVER (PARTITION BY person_id ORDER BY start_at DESC) = 1
),

enhanced AS (
    SELECT
        CAST(persons.person_id AS INTEGER) AS person_id,
        CAST(persons.full_name AS VARCHAR) AS full_name,
        CAST(persons.first_name AS VARCHAR) AS first_name,
        CAST(persons.last_name AS VARCHAR) AS last_name,
        CAST(persons.gender AS VARCHAR) AS gender,
        CAST(persons.email AS VARCHAR) AS email,
        CAST(persons.is_current AS BOOLEAN) AS is_current_mk,
        CAST(mk_terms.person_id IS NOT NULL AS BOOLEAN) AS was_mk_in_scope,
        CAST(mk_terms.first_knesset_num AS INTEGER) AS first_knesset_num,
        CAST(mk_terms.last_knesset_num AS INTEGER) AS last_knesset_num,
        CAST(COALESCE(mk_terms.knessets_served, 0) AS INTEGER) AS knessets_served,
        CAST(latest_memberships.faction_id AS INTEGER) AS latest_faction_id,
        CAST(latest_memberships.faction_name AS VARCHAR) AS latest_faction_name
    FROM persons
    LEFT JOIN mk_terms
        ON persons.person_id = mk_terms.person_id
    LEFT JOIN latest_memberships
        ON persons.person_id = latest_memberships.person_id
)

SELECT *
FROM enhanced
