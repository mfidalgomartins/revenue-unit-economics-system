select
    cast(date as date) as spend_date,
    cast(acquisition_channel as varchar) as acquisition_channel,
    cast(spend as double precision) as spend
from {{ source('raw', 'marketing_spend') }}
