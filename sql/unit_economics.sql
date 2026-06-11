-- Reference transformation for unit_economics (DuckDB-style SQL)
WITH cust AS (
  SELECT
    acquisition_channel,
    COUNT(*) AS customers_acquired
  FROM customers
  GROUP BY acquisition_channel
),
spend AS (
  SELECT
    acquisition_channel,
    SUM(spend) AS total_spend
  FROM marketing_spend
  GROUP BY acquisition_channel
),
ltv AS (
  SELECT
    acquisition_channel,
    AVG(contribution_margin) AS average_LTV,
    MEDIAN(contribution_margin) AS median_LTV,
    SUM(contribution_margin) AS total_contribution
  FROM customer_metrics
  GROUP BY acquisition_channel
),
months AS (
  SELECT COUNT(DISTINCT DATE_TRUNC('month', date)) AS observed_months
  FROM marketing_spend
)
SELECT
  c.acquisition_channel,
  c.customers_acquired,
  s.total_spend,
  s.total_spend / NULLIF(c.customers_acquired, 0) AS CAC,
  l.average_LTV,
  l.median_LTV,
  l.total_contribution AS total_channel_contribution_margin,
  l.average_LTV / NULLIF(s.total_spend / NULLIF(c.customers_acquired, 0), 0) AS LTV_to_CAC,
  CASE
    WHEN (l.total_contribution / NULLIF(m.observed_months, 0)) / NULLIF(c.customers_acquired, 0) <= 0 THEN NULL
    ELSE (s.total_spend / NULLIF(c.customers_acquired, 0)) /
      ((l.total_contribution / NULLIF(m.observed_months, 0)) / NULLIF(c.customers_acquired, 0))
  END AS approximate_payback_period
FROM cust c
JOIN spend s USING (acquisition_channel)
JOIN ltv l USING (acquisition_channel)
CROSS JOIN months m;
