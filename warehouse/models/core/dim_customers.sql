{{
    config(
        materialized='table',
        contract={'enforced': true},
        meta={'owner': 'analytics-engineering', 'sla_hours': 24}
    )
}}

select
    customer_id,
    signup_date,
    segment,
    region,
    acquisition_channel
from {{ ref('stg_customers') }}
