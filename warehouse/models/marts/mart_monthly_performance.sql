with transaction_months as (
    select
        date_trunc('month', transaction_date) as metric_month,
        sum(revenue) as revenue,
        sum(cost) as direct_cost,
        sum(revenue - cost) as contribution_margin,
        count(*) as transactions,
        count(distinct customer_id) as active_customers
    from {{ ref('fct_transactions') }}
    group by 1
),
spend_months as (
    select
        date_trunc('month', spend_date) as metric_month,
        sum(spend) as marketing_spend
    from {{ ref('fct_marketing_spend') }}
    group by 1
)
select
    t.metric_month,
    t.revenue,
    t.direct_cost,
    t.contribution_margin,
    t.contribution_margin / nullif(t.revenue, 0) as contribution_margin_rate,
    t.transactions,
    t.active_customers,
    coalesce(s.marketing_spend, 0) as marketing_spend
from transaction_months t
left join spend_months s using (metric_month)
order by metric_month
