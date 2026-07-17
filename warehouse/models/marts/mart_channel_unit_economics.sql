with customers as (
    select
        acquisition_channel,
        count(*) as customers_acquired
    from {{ ref('dim_customers') }}
    group by 1
),
contribution as (
    select
        c.acquisition_channel,
        sum(t.revenue - t.cost) as total_contribution_margin
    from {{ ref('fct_transactions') }} t
    inner join {{ ref('dim_customers') }} c using (customer_id)
    group by 1
),
spend as (
    select
        acquisition_channel,
        sum(spend) as total_spend
    from {{ ref('fct_marketing_spend') }}
    group by 1
)
select
    c.acquisition_channel,
    c.customers_acquired,
    coalesce(s.total_spend, 0) as total_spend,
    coalesce(s.total_spend, 0) / nullif(c.customers_acquired, 0) as cac,
    coalesce(m.total_contribution_margin, 0) as total_contribution_margin,
    coalesce(m.total_contribution_margin, 0) / nullif(c.customers_acquired, 0) as average_ltv,
    (
        coalesce(m.total_contribution_margin, 0) / nullif(c.customers_acquired, 0)
    ) / nullif(coalesce(s.total_spend, 0) / nullif(c.customers_acquired, 0), 0) as ltv_to_cac
from customers c
left join contribution m using (acquisition_channel)
left join spend s using (acquisition_channel)
order by c.acquisition_channel
