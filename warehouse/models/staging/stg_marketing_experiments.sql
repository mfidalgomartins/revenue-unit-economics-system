select
    cast(experiment_id as varchar) as experiment_id,
    cast(customer_id as varchar) as customer_id,
    cast(acquisition_channel as varchar) as acquisition_channel,
    cast(assignment as varchar) as assignment,
    cast(assigned_date as date) as assigned_date,
    cast(outcome_window_days as integer) as outcome_window_days,
    cast(converted as boolean) as converted,
    cast(pre_period_contribution as double precision) as pre_period_contribution,
    cast(observed_contribution as double precision) as observed_contribution
from {{ source('raw', 'marketing_experiments') }}
