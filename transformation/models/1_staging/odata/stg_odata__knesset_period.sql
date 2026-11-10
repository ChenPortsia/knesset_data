-- Knesset terms split into assemblies and sittings | כנסות לפי כנסים ומושבים
-- Grain: one row per Knesset sitting period

WITH source AS (
    SELECT *
    FROM {{ source('odata', 'kns_knesset_dates') }}
),

renamed AS (
    SELECT
        CAST(id AS INTEGER)                                  AS knesset_period_id,
        CAST(knesset_num AS INTEGER)                         AS knesset_num,
        CAST(name AS VARCHAR)                                AS knesset_name,
        CAST(assembly AS INTEGER)                            AS assembly,
        CAST(plenum AS INTEGER)                              AS plenum,
        CAST({{ local_time('plenum_start') }} AS TIMESTAMP)  AS start_at,
        CAST({{ local_time('plenum_finish') }} AS TIMESTAMP) AS finish_at,
        CAST(is_current AS BOOLEAN)                          AS is_current,
        CAST(last_updated_date AS TIMESTAMPTZ)               AS updated_at,
        CAST(_dlt_valid_from AS TIMESTAMPTZ)                 AS loaded_at,
        CAST(_dlt_valid_to AS TIMESTAMPTZ)                   AS valid_to
    FROM source
),

filtered AS (
    SELECT *
    FROM renamed
    WHERE {{ is_current('kns_knesset_dates', 'knesset_period_id') }}
),

enhanced AS (
    SELECT
        *
    FROM filtered
)

SELECT * EXCLUDE (valid_to)
FROM enhanced
