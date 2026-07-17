select
    cast(intervention_id as varchar) as intervention_id,
    cast(week_start as date) as week_start,
    cast(product_type as varchar) as product_type,
    cast(region as varchar) as region,
    cast(assignment as varchar) as assignment,
    cast(reference_price as double precision) as reference_price,
    cast(observed_price as double precision) as observed_price,
    cast(units_sold as integer) as units_sold,
    cast(revenue as double precision) as revenue,
    cast(contribution_margin as double precision) as contribution_margin
from {{ source('raw', 'pricing_interventions') }}
