-- Reference transformation for customer_metrics (DuckDB-style SQL)
WITH tx AS (
  SELECT
    customer_id,
    MIN(transaction_date) AS first_transaction_date,
    MAX(transaction_date) AS last_transaction_date,
    SUM(revenue) AS total_revenue,
    SUM(cost) AS total_cost,
    COUNT(*) AS transaction_count
  FROM transactions
  GROUP BY customer_id
),
base AS (
  SELECT
    c.customer_id,
    c.segment,
    c.region,
    c.acquisition_channel,
    t.first_transaction_date,
    t.last_transaction_date,
    CASE WHEN COALESCE(t.transaction_count, 0) > 0
      THEN DATE_DIFF('day', t.first_transaction_date, t.last_transaction_date) + 1
      ELSE 0
    END AS transaction_span_days,
    COALESCE(t.total_revenue, 0) AS total_revenue,
    COALESCE(t.total_cost, 0) AS total_cost,
    COALESCE(t.total_revenue, 0) - COALESCE(t.total_cost, 0) AS contribution_margin,
    CASE WHEN COALESCE(t.total_revenue, 0) > 0
      THEN (COALESCE(t.total_revenue, 0) - COALESCE(t.total_cost, 0)) / COALESCE(t.total_revenue, 0)
      ELSE 0
    END AS contribution_margin_pct,
    COALESCE(t.transaction_count, 0) AS transaction_count,
    CASE WHEN COALESCE(t.transaction_count, 0) > 0
      THEN COALESCE(t.total_revenue, 0) / COALESCE(t.transaction_count, 1)
      ELSE 0
    END AS avg_revenue_per_transaction,
    CASE WHEN COALESCE(t.transaction_count, 0) > 0
      THEN COALESCE(t.total_revenue, 0) / (DATE_DIFF('day', t.first_transaction_date, t.last_transaction_date) + 1)
      ELSE 0
    END AS revenue_per_transaction_span_day
  FROM customers c
  LEFT JOIN tx t ON c.customer_id = t.customer_id
)
SELECT * FROM base;
