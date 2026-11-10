{# Convert a UTC timestamp to Israel local time, so dates match the Knesset calendar. #}
{% macro local_time(column) -%}
    timezone('Asia/Jerusalem', {{ column }})
{%- endmacro %}
