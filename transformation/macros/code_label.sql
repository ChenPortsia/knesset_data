{# English label for a source code, from the code_labels seed. #}
{% macro code_label(domain, column) -%}
    (
        SELECT label_en
        FROM {{ ref('code_labels') }}
        WHERE domain = '{{ domain }}' AND code = {{ column }}
    )
{%- endmacro %}
