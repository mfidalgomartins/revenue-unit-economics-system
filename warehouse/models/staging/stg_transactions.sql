select
    cast(transaction_id as varchar) as transaction_id,
    cast(customer_id as varchar) as customer_id,
    cast(transaction_date as date) as transaction_date,
    cast(revenue as double precision) as revenue,
    cast(cost as double precision) as cost,
    cast(product_type as varchar) as product_type
from {{ source('raw', 'transactions') }}
