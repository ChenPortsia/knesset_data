{#
  Filter for staging models over SCD2 bronze tables: keep the current version of each
  row (bronze keeps every version) and drop rows the weekly check found deleted in the API.
  Use in the `filtered` CTE, after `renamed` has cast _dlt_valid_to AS valid_to.
#}
{% macro is_current(table, key) -%}
    valid_to IS NULL
    AND {{ key }} NOT IN (
        SELECT CAST(id AS INTEGER)
        FROM {{ source('odata', 'deleted_ids') }}
        WHERE table_name = '{{ table }}'
    )
{%- endmacro %}
