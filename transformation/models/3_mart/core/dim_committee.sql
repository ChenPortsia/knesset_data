-- Knesset committees per Knesset | ועדות הכנסת בכל כנסת
-- Grain: one row per committee (a committee belongs to one Knesset)

WITH committees AS (
    SELECT *
    FROM {{ ref('stg_odata__committee') }}
),

enhanced AS (
    SELECT
        CAST(committee_id AS INTEGER) AS committee_id,
        CAST(committee_name AS VARCHAR) AS committee_name,
        CAST(knesset_num AS INTEGER) AS knesset_num,
        CAST(category_id AS INTEGER) AS category_id,
        CAST(category_name AS VARCHAR) AS category_name,
        CAST(committee_type AS VARCHAR) AS committee_type,
        CAST(additional_type AS VARCHAR) AS additional_type,
        CAST(parent_committee_id AS INTEGER) AS parent_committee_id,
        CAST(parent_committee_name AS VARCHAR) AS parent_committee_name,
        CAST(start_at AS TIMESTAMP) AS start_at,
        CAST(finish_at AS TIMESTAMP) AS finish_at,
        CAST(is_current AS BOOLEAN) AS is_current
    FROM committees
)

SELECT *
FROM enhanced
