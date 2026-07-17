{{
    config(
        materialized='incremental',
        incremental_strategy='delete+insert',
        unique_key='transaction_id',
        on_schema_change='fail',
        contract={'enforced': true},
        meta={'owner': 'analytics-engineering', 'sla_hours': 6, 'late_arrival_lookback_days': 30}
    )
}}

select
    transaction_id,
    customer_id,
    transaction_date,
    revenue,
    cost,
    product_type
from {{ ref('stg_transactions') }}
{% if is_incremental() %}
where transaction_date >= (
    select coalesce(max(transaction_date), cast('1900-01-01' as date))
           - interval '{{ var("incremental_lookback_days") }} day'
    from {{ this }}
)
{% endif %}
