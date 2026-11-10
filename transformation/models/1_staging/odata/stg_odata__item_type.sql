-- Types of items discussed in sessions | סוגי פריטים הנדונים בישיבות
-- Grain: one row per item type

WITH source AS (
    SELECT *
    FROM {{ source('odata', 'kns_item_type') }}
),

renamed AS (
    SELECT
        CAST(id AS INTEGER)         AS item_type_id,
        CAST("desc" AS VARCHAR)     AS item_type_name,
        CAST(table_name AS VARCHAR) AS source_table
    FROM source
),

filtered AS (
    SELECT *
    FROM renamed
    -- fully replaced on every load: every row is current
),

enhanced AS (
    SELECT
        *
    FROM filtered
)

SELECT *
FROM enhanced
