-- Each (domain, code) pair must have exactly one label, or code_label() would fail.
select domain, code, count(*) as n
from {{ ref('code_labels') }}
group by all
having count(*) > 1
