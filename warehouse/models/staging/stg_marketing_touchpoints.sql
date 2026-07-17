select
    cast(touchpoint_id as varchar) as touchpoint_id,
    cast(customer_id as varchar) as customer_id,
    cast(touchpoint_date as date) as touchpoint_date,
    cast(acquisition_channel as varchar) as acquisition_channel,
    cast(touchpoint_order as integer) as touchpoint_order,
    cast(is_conversion_touch as boolean) as is_conversion_touch
from {{ source('raw', 'marketing_touchpoints') }}
