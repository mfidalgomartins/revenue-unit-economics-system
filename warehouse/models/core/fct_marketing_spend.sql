{{
    config(
        materialized='incremental',
        incremental_strategy='delete+insert',
        unique_key=['spend_date', 'acquisition_channel'],
        on_schema_change='fail',
        contract={'enforced': true},
        meta={'owner': 'growth-analytics', 'sla_hours': 24, 'late_arrival_lookback_days': 30}
    )
}}

select
    spend_date,
    acquisition_channel,
    spend
from {{ ref('stg_marketing_spend') }}
{% if is_incremental() %}
where spend_date >= (
    select coalesce(max(spend_date), cast('1900-01-01' as date))
           - interval '{{ var("incremental_lookback_days") }} day'
    from {{ this }}
)
{% endif %}
