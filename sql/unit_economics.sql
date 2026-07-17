-- Reference transformation for unit_economics (DuckDB-style SQL)
WITH parameters AS (
  SELECT 24::INTEGER AS payback_horizon_months
),
observation_candidates AS (
  SELECT MAX(DATE_TRUNC('month', signup_date)) AS observation_month FROM customers
  UNION ALL
  SELECT MAX(DATE_TRUNC('month', transaction_date)) AS observation_month FROM transactions
  UNION ALL
  SELECT MAX(DATE_TRUNC('month', date)) AS observation_month FROM marketing_spend
),
observation AS (
  SELECT MAX(observation_month) AS observation_month
  FROM observation_candidates
),
cust AS (
  SELECT
    acquisition_channel,
    COUNT(DISTINCT customer_id) AS customers_acquired
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
unit_base AS (
  SELECT
    c.acquisition_channel,
    c.customers_acquired,
    COALESCE(s.total_spend, 0) AS total_spend,
    COALESCE(s.total_spend, 0) / NULLIF(c.customers_acquired, 0) AS CAC,
    COALESCE(l.average_LTV, 0) AS average_LTV,
    COALESCE(l.median_LTV, 0) AS median_LTV,
    COALESCE(l.total_contribution, 0) AS total_channel_contribution_margin,
    COALESCE(l.average_LTV, 0)
      / NULLIF(COALESCE(s.total_spend, 0) / NULLIF(c.customers_acquired, 0), 0)
      AS LTV_to_CAC
  FROM cust c
  LEFT JOIN spend s USING (acquisition_channel)
  LEFT JOIN ltv l USING (acquisition_channel)
),
mature_customers AS (
  SELECT
    c.customer_id,
    c.acquisition_channel,
    c.signup_date,
    DATE_TRUNC('month', c.signup_date) AS cohort_month
  FROM customers c
  CROSS JOIN observation o
  CROSS JOIN parameters p
  WHERE DATE_DIFF(
    'month',
    DATE_TRUNC('month', c.signup_date),
    o.observation_month
  ) >= p.payback_horizon_months
),
mature_counts AS (
  SELECT
    acquisition_channel,
    COUNT(DISTINCT customer_id) AS payback_mature_customers
  FROM mature_customers
  GROUP BY acquisition_channel
),
acquisition_windows AS (
  SELECT
    acquisition_channel,
    MIN(signup_date) AS payback_acquisition_start,
    MAX(signup_date) AS payback_acquisition_end
  FROM mature_customers
  GROUP BY acquisition_channel
),
aligned_spend AS (
  SELECT
    w.acquisition_channel,
    SUM(s.spend) AS payback_aligned_spend
  FROM acquisition_windows w
  LEFT JOIN marketing_spend s
    ON w.acquisition_channel = s.acquisition_channel
    AND s.date BETWEEN w.payback_acquisition_start AND w.payback_acquisition_end
  GROUP BY w.acquisition_channel
),
payback_cac AS (
  SELECT
    w.acquisition_channel,
    w.payback_acquisition_start,
    w.payback_acquisition_end,
    m.payback_mature_customers,
    s.payback_aligned_spend,
    s.payback_aligned_spend / NULLIF(m.payback_mature_customers, 0) AS payback_cac
  FROM acquisition_windows w
  JOIN mature_counts m USING (acquisition_channel)
  LEFT JOIN aligned_spend s USING (acquisition_channel)
),
age_grid AS (
  SELECT ages.age_month::INTEGER AS age_month
  FROM parameters p,
    RANGE(0, p.payback_horizon_months + 1) AS ages(age_month)
),
mature_monthly_contribution AS (
  SELECT
    m.acquisition_channel,
    DATE_DIFF(
      'month',
      m.cohort_month,
      DATE_TRUNC('month', t.transaction_date)
    )::INTEGER AS age_month,
    SUM(t.revenue - t.cost) AS contribution_margin
  FROM mature_customers m
  JOIN transactions t USING (customer_id)
  CROSS JOIN parameters p
  WHERE DATE_DIFF(
    'month',
    m.cohort_month,
    DATE_TRUNC('month', t.transaction_date)
  ) BETWEEN 0 AND p.payback_horizon_months
  GROUP BY m.acquisition_channel, age_month
),
curve_monthly AS (
  SELECT
    u.acquisition_channel,
    ages.age_month,
    p.payback_cac,
    COALESCE(m.payback_mature_customers, 0) AS payback_mature_customers,
    COALESCE(c.contribution_margin, 0) AS contribution_margin
  FROM unit_base u
  CROSS JOIN age_grid ages
  LEFT JOIN mature_counts m USING (acquisition_channel)
  LEFT JOIN payback_cac p USING (acquisition_channel)
  LEFT JOIN mature_monthly_contribution c
    ON u.acquisition_channel = c.acquisition_channel
    AND ages.age_month = c.age_month
),
curve AS (
  SELECT
    acquisition_channel,
    age_month,
    payback_cac,
    payback_mature_customers,
    SUM(contribution_margin) OVER (
      PARTITION BY acquisition_channel
      ORDER BY age_month
      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) / NULLIF(payback_mature_customers, 0)
      AS cumulative_contribution_per_customer
  FROM curve_monthly
),
payback AS (
  SELECT
    acquisition_channel,
    MAX(payback_mature_customers) AS payback_mature_customers,
    MIN(age_month) FILTER (
      WHERE cumulative_contribution_per_customer >= payback_cac
    ) AS approximate_payback_period,
    MAX(cumulative_contribution_per_customer) FILTER (
      WHERE age_month = (SELECT payback_horizon_months FROM parameters)
    ) AS payback_horizon_contribution_per_customer
  FROM curve
  GROUP BY acquisition_channel
)
SELECT
  u.acquisition_channel,
  u.customers_acquired,
  u.total_spend,
  u.CAC,
  u.average_LTV,
  u.median_LTV,
  u.total_channel_contribution_margin,
  u.LTV_to_CAC,
  pc.payback_cac,
  pc.payback_aligned_spend,
  pc.payback_acquisition_start,
  pc.payback_acquisition_end,
  p.approximate_payback_period,
  CASE
    WHEN COALESCE(p.payback_mature_customers, 0) = 0 THEN 'insufficient_maturity'
    WHEN pc.payback_cac IS NULL THEN 'insufficient_spend_alignment'
    WHEN p.approximate_payback_period IS NOT NULL THEN 'recovered'
    ELSE 'not_recovered'
  END AS payback_status,
  CASE
    WHEN COALESCE(p.payback_mature_customers, 0) > 0
      AND pc.payback_cac IS NOT NULL
      AND p.approximate_payback_period IS NULL THEN TRUE
    ELSE FALSE
  END AS payback_is_censored,
  cfg.payback_horizon_months,
  COALESCE(p.payback_mature_customers, 0) AS payback_mature_customers,
  COALESCE(p.payback_mature_customers, 0) / NULLIF(u.customers_acquired, 0)
    AS payback_mature_customer_share,
  p.payback_horizon_contribution_per_customer
FROM unit_base u
LEFT JOIN payback p USING (acquisition_channel)
LEFT JOIN payback_cac pc USING (acquisition_channel)
CROSS JOIN parameters cfg;
