-- Plenum votes with the item voted on (bill, motion...) | הצבעות במליאה עם הפריט שעליו הצביעו
-- Grain: one row per vote
-- A vote's item_id is the id of the item itself (a bill id for bills); the plenum session
-- agenda says which type of item it is.

WITH votes AS (
    SELECT *
    FROM {{ ref('stg_odata__plenum_vote') }}
),

plenum_session_items AS (
    SELECT *
    FROM {{ ref('stg_odata__plenum_session_item') }}
),

items_per_session AS (
    -- An item can appear more than once on a session's agenda: one row per session and item,
    -- so the join below cannot multiply votes
    SELECT
        plenum_session_id,
        item_id,
        MIN(item_type_id) AS item_type_id,
        MIN(item_type) AS item_type
    FROM plenum_session_items
    GROUP BY plenum_session_id, item_id
),

enhanced AS (
    SELECT
        CAST(votes.vote_id AS INTEGER) AS vote_id,
        CAST(votes.plenum_session_id AS INTEGER) AS plenum_session_id,
        CAST(votes.voted_at AS TIMESTAMP) AS voted_at,
        CAST(votes.vote_title AS VARCHAR) AS vote_title,
        CAST(votes.vote_subject AS VARCHAR) AS vote_subject,
        CAST(votes.vote_method AS VARCHAR) AS vote_method,
        CAST(votes.is_no_confidence AS BOOLEAN) AS is_no_confidence,
        CAST(votes.for_option AS VARCHAR) AS for_option,
        CAST(votes.against_option AS VARCHAR) AS against_option,
        CAST(votes.item_id AS INTEGER) AS item_id,
        CAST(items_per_session.item_type_id AS INTEGER) AS item_type_id,
        CAST(items_per_session.item_type AS VARCHAR) AS item_type,
        CAST(CASE WHEN items_per_session.item_type_id = 2 THEN votes.item_id END AS INTEGER) AS bill_id
    FROM votes
    LEFT JOIN items_per_session
        ON votes.plenum_session_id = items_per_session.plenum_session_id
        AND votes.item_id = items_per_session.item_id
)

SELECT *
FROM enhanced
