-- J9: How many no-confidence votes did each Knesset hold, and how close did the closest come?
-- A no-confidence motion needs 61 votes in favour to pass. Votes on a bill that were also
-- declared a confidence vote (item_type is set) are left out: 'for' there is for the bill.

WITH plenum_votes AS (
    SELECT *
    FROM {{ ref('fct_plenum_vote') }}
),

filtered AS (
    SELECT *
    FROM plenum_votes
    WHERE is_no_confidence
      AND item_type IS NULL
),

enhanced AS (
    SELECT
        knesset_num,
        COUNT(*) AS no_confidence_votes,
        MAX(votes_for) AS most_votes_for,
        COUNT(*) FILTER (WHERE votes_for >= 61) AS reached_61
    FROM filtered
    GROUP BY knesset_num
)

SELECT *
FROM enhanced
ORDER BY knesset_num
