{# English label for a source code, from the code_labels seed. #}
{% macro code_label(domain, column) -%}
    (select label_en from {{ ref('code_labels') }} where domain = '{{ domain }}' and code = {{ column }})
{%- endmacro %}
