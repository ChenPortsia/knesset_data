{#
  Current version of each row of an SCD2 bronze table: bronze keeps every version
  (_dlt_valid_to is null for the current one). Rows the weekly check found deleted
  in the API are left out.
#}
{% macro current_rows(table) -%}
(
    select *
    from {{ source('odata', table) }}
    where _dlt_valid_to is null
      and id not in (select id from {{ source('odata', 'deleted_ids') }} where table_name = '{{ table }}')
)
{%- endmacro %}
