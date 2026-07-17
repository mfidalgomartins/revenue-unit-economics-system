select
    cast(customer_id as varchar) as customer_id,
    cast(signup_date as date) as signup_date,
    cast(segment as varchar) as segment,
    cast(region as varchar) as region,
    cast(acquisition_channel as varchar) as acquisition_channel
from {{ source('raw', 'customers') }}
