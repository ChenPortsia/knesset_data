{#
  A person's name in a form that compares well: no apostrophes or quote marks
  (יחימוביץ' = יחימוביץ), hyphens as spaces, single spaces.
#}
{% macro name_key(column) -%}
    TRIM(REGEXP_REPLACE(REGEXP_REPLACE(REPLACE({{ column }}, '-', ' '), '[''"`׳״]', '', 'g'), '\s+', ' ', 'g'))
{%- endmacro %}
