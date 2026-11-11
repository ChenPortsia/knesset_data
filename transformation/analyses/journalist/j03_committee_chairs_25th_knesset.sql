-- J3: Who chaired each main committee in the 25th Knesset, and for how long?

WITH roles AS (
    SELECT *
    FROM {{ ref('fct_person_role') }}
),

persons AS (
    SELECT *
    FROM {{ ref('dim_person') }}
),

filtered AS (
    SELECT *
    FROM roles
    WHERE role = 'committee_chair'
      AND knesset_num = 25
),

enhanced AS (
    SELECT
        filtered.committee_name,
        persons.full_name AS chair,
        persons.latest_faction_name,
        filtered.start_date,
        filtered.finish_date,
        filtered.days_in_role
    FROM filtered
    INNER JOIN persons
        ON filtered.person_id = persons.person_id
)

SELECT *
FROM enhanced
ORDER BY days_in_role DESC
LIMIT 12
