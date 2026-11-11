-- Who held which role, when: committee chairs and members, ministers, Speaker, opposition leader | מי מילא איזה תפקיד ומתי
-- Grain: one row per person, role, committee or ministry, government and continuous period

WITH roles AS (
    SELECT *
    FROM {{ ref('int_person_roles_classified') }}
),

committees AS (
    SELECT *
    FROM {{ ref('stg_odata__committee') }}
),

ministries AS (
    SELECT *
    FROM {{ ref('stg_odata__ministry') }}
),

enhanced AS (
    SELECT
        CAST(roles.person_role_id AS VARCHAR) AS person_role_id,
        CAST(roles.person_id AS INTEGER) AS person_id,
        CAST(roles.role AS VARCHAR) AS role,
        CAST(roles.role_group AS VARCHAR) AS role_group,
        CAST(roles.knesset_num AS INTEGER) AS knesset_num,
        CAST(roles.committee_id AS INTEGER) AS committee_id,
        CAST(committees.committee_name AS VARCHAR) AS committee_name,
        CAST(roles.ministry_id AS INTEGER) AS ministry_id,
        CAST(ministries.ministry_name AS VARCHAR) AS ministry_name,
        CAST(roles.government_num AS INTEGER) AS government_num,
        CAST(CAST(roles.start_at AS DATE) AS DATE) AS start_date,
        CAST(CAST(roles.finish_at AS DATE) AS DATE) AS finish_date,
        CAST(DATE_DIFF('day', roles.start_at, COALESCE(roles.finish_at, CURRENT_TIMESTAMP)) AS INTEGER) AS days_in_role,
        CAST(roles.finish_at IS NULL AS BOOLEAN) AS is_current
    FROM roles
    LEFT JOIN committees
        ON roles.committee_id = committees.committee_id
    LEFT JOIN ministries
        ON roles.ministry_id = ministries.ministry_id
)

SELECT *
FROM enhanced
