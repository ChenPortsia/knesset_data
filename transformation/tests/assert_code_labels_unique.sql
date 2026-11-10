-- Each (domain, code) pair must have exactly one label, or code_label() would fail.
SELECT
    domain,
    code,
    COUNT(*) AS n
FROM {{ ref('code_labels') }}
GROUP BY ALL
HAVING COUNT(*) > 1
