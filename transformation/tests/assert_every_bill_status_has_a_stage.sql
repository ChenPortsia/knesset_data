-- Every bill status used by a bill needs a row in the bill_status_stages seed.
-- When this warns, add the new status to seeds/bill_status_stages.csv.
{{ config(severity='warn') }}

SELECT
    status_id,
    status_he,
    COUNT(*) AS bills
FROM {{ ref('int_bills_joined_to_stages') }}
WHERE stage IS NULL
GROUP BY ALL
