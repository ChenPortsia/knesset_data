-- Q9: Share of women among MKs in each Knesset since the 20th

WITH memberships AS (
    SELECT *
    FROM {{ ref('fct_faction_membership') }}
),

persons AS (
    SELECT *
    FROM {{ ref('dim_person') }}
),

mks_per_knesset AS (
    -- An MK is anyone who was a faction member in that Knesset
    SELECT DISTINCT
        memberships.knesset_num,
        memberships.person_id
    FROM memberships
),

enhanced AS (
    SELECT
        mks_per_knesset.knesset_num,
        COUNT(*) AS mks,
        COUNT(*) FILTER (WHERE persons.gender = 'female') AS women,
        ROUND(100.0 * COUNT(*) FILTER (WHERE persons.gender = 'female') / COUNT(*), 1) AS women_percent
    FROM mks_per_knesset
    INNER JOIN persons
        ON mks_per_knesset.person_id = persons.person_id
    GROUP BY mks_per_knesset.knesset_num
)

SELECT *
FROM enhanced
ORDER BY knesset_num
