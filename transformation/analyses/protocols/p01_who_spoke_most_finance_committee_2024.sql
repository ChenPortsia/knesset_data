-- P1: Which MKs spoke the most in the Finance Committee in 2024?
-- Counted in words, from the sessions whose protocols are loaded.

WITH turns AS (
    SELECT *
    FROM {{ ref('fct_turn') }}
),

committees AS (
    SELECT *
    FROM {{ ref('dim_committee') }}
),

persons AS (
    SELECT *
    FROM {{ ref('dim_person') }}
),

filtered AS (
    SELECT turns.*
    FROM turns
    INNER JOIN committees
        ON turns.committee_id = committees.committee_id
    WHERE committees.category_name = 'ועדת הכספים'
      AND committees.committee_type = 'ועדה ראשית'
      AND YEAR(turns.session_date) = 2024
      AND turns.person_id IS NOT NULL
),

enhanced AS (
    SELECT
        persons.full_name,
        COUNT(DISTINCT filtered.committee_session_id) AS sessions,
        COUNT(*) AS turns,
        SUM(filtered.words) AS words,
        ROUND(100.0 * SUM(filtered.words) / SUM(SUM(filtered.words)) OVER (), 1) AS percent_of_mk_words
    FROM filtered
    INNER JOIN persons
        ON filtered.person_id = persons.person_id
    GROUP BY persons.full_name
)

SELECT *
FROM enhanced
ORDER BY words DESC, full_name
LIMIT 10
