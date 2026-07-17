"""Generate a lightweight business-facing data catalog for governance."""

from __future__ import annotations

import pandas as pd

from src.paths import PROJECT_ROOT, RAW_DATA_DIR

RAW_DIR = RAW_DATA_DIR
PROC_DIR = PROJECT_ROOT / "data" / "processed"
OUT_TABLES_DIR = PROJECT_ROOT / "outputs" / "tables"

DATASETS = [
    ("raw", "customers", RAW_DIR / "customers.csv"),
    ("raw", "transactions", RAW_DIR / "transactions.csv"),
    ("raw", "marketing_spend", RAW_DIR / "marketing_spend.csv"),
    ("raw", "marketing_touchpoints", RAW_DIR / "marketing_touchpoints.csv"),
    ("raw", "marketing_experiments", RAW_DIR / "marketing_experiments.csv"),
    ("raw", "pricing_interventions", RAW_DIR / "pricing_interventions.csv"),
    ("processed", "customer_metrics", PROC_DIR / "customer_metrics.csv"),
    ("processed", "cohort_table", PROC_DIR / "cohort_table.csv"),
    ("processed", "unit_economics", PROC_DIR / "unit_economics.csv"),
    ("output", "raw_validation_summary", OUT_TABLES_DIR / "raw_validation_summary.csv"),
    ("output", "data_profile_summary", OUT_TABLES_DIR / "data_profile_summary.csv"),
    ("output", "data_quality_issues", OUT_TABLES_DIR / "data_quality_issues.csv"),
    ("output", "monthly_revenue_health", OUT_TABLES_DIR / "monthly_revenue_health.csv"),
    (
        "output",
        "revenue_decomposition_effects",
        OUT_TABLES_DIR / "revenue_decomposition_effects.csv",
    ),
    (
        "output",
        "cohort_retention_summary",
        OUT_TABLES_DIR / "cohort_retention_summary.csv",
    ),
    (
        "output",
        "unit_economics_channel_diagnostics",
        OUT_TABLES_DIR / "unit_economics_channel_diagnostics.csv",
    ),
    ("output", "segment_profitability", OUT_TABLES_DIR / "segment_profitability.csv"),
    ("output", "region_profitability", OUT_TABLES_DIR / "region_profitability.csv"),
    ("output", "product_profitability", OUT_TABLES_DIR / "product_profitability.csv"),
    (
        "output",
        "low_margin_growth_pockets",
        OUT_TABLES_DIR / "low_margin_growth_pockets.csv",
    ),
    ("output", "main_analysis_findings", OUT_TABLES_DIR / "main_analysis_findings.csv"),
    ("output", "marketing_incrementality", OUT_TABLES_DIR / "marketing_incrementality.csv"),
    ("output", "multi_touch_attribution", OUT_TABLES_DIR / "multi_touch_attribution.csv"),
    ("output", "pricing_elasticity", OUT_TABLES_DIR / "pricing_elasticity.csv"),
    ("output", "pricing_recommendations", OUT_TABLES_DIR / "pricing_recommendations.csv"),
    ("output", "scenario_reallocation_plan", OUT_TABLES_DIR / "scenario_reallocation_plan.csv"),
    (
        "output",
        "scenario_outcomes_summary",
        OUT_TABLES_DIR / "scenario_outcomes_summary.csv",
    ),
    (
        "output",
        "scenario_stress_test_summary",
        OUT_TABLES_DIR / "scenario_stress_test_summary.csv",
    ),
    (
        "output",
        "scenario_seed_sensitivity",
        OUT_TABLES_DIR / "scenario_seed_sensitivity.csv",
    ),
    (
        "output",
        "scenario_seed_sensitivity_summary",
        OUT_TABLES_DIR / "scenario_seed_sensitivity_summary.csv",
    ),
]

FIELD_DEFINITIONS: dict[str, tuple[str, str]] = {
    # Identifiers
    "customer_id": (
        "Unique customer identifier.",
        "Join key across customer and transaction views.",
    ),
    "transaction_id": (
        "Unique transaction identifier.",
        "Duplicate control on transactional facts.",
    ),
    "touchpoint_id": (
        "Unique identifier for a governed pre-signup marketing interaction.",
        "Journey ordering and attribution reconciliation.",
    ),
    "experiment_id": (
        "Stable identifier for a randomized marketing holdout.",
        "Experiment-level balance and lift estimation.",
    ),
    "intervention_id": (
        "Unique identifier for a randomized weekly pricing cell.",
        "Intervention-grain uniqueness and auditability.",
    ),
    # Dimensions
    "segment": (
        "Customer segment (Startup, SMB, Mid-Market, Enterprise).",
        "Cross-cut for margin and retention diagnostics.",
    ),
    "region": (
        "Customer region (North America, EMEA, LATAM, APAC).",
        "Geographic mix and regional profitability.",
    ),
    "acquisition_channel": (
        "Channel attributed to customer acquisition.",
        "Unit economics and budget allocation.",
    ),
    "product_type": (
        "Product line for the transaction.",
        "Product mix and profitability analysis.",
    ),
    # Temporal
    "signup_date": ("Date the customer first signed up.", "Cohort assignment."),
    "transaction_date": ("Date the transaction occurred.", "Time-series aggregation."),
    "date": ("Calendar date.", "Time-series aggregation."),
    "cohort_month": ("Signup month used as cohort key.", "Cohort retention analysis."),
    "activity_month": (
        "Calendar month evaluated for the cohort, including zero-activity months.",
        "Cohort activity and retention curve x-axis.",
    ),
    "month": ("Calendar month, first-of-month timestamp.", "Monthly aggregation."),
    "first_transaction_date": (
        "First observed transaction for the customer.",
        "Observed transaction-span start.",
    ),
    "last_transaction_date": (
        "Last observed transaction for the customer.",
        "Observed transaction-span end.",
    ),
    "touchpoint_date": (
        "Date of a privacy-minimal marketing interaction before signup.",
        "Journey ordering without storing contact details.",
    ),
    "assigned_date": (
        "Date a customer entered a randomized experiment arm.",
        "Experiment exposure and outcome-window governance.",
    ),
    "week_start": (
        "Monday starting the randomized pricing measurement week.",
        "Pricing-panel time index and fixed effects.",
    ),
    "date_min": ("Earliest observed date in the profiled table.", "Coverage and freshness review."),
    "date_max": ("Latest observed date in the profiled table.", "Coverage and freshness review."),
    "months_since_cohort": (
        "Completed months between signup cohort and activity month.",
        "Cohort-retention age axis.",
    ),
    "cohorts_observed": (
        "Number of mature signup cohorts contributing to the age-level estimate.",
        "Maturity and sample-size context for retention.",
    ),
    # Money / counts
    "revenue": ("Gross revenue booked on the transaction.", "Top-line growth and mix."),
    "cost": (
        "Direct delivery cost linked to the transaction.",
        "Contribution margin and unit economics.",
    ),
    "spend": ("Marketing spend recorded for the day and channel.", "CAC and channel ROI."),
    "total_revenue": ("Sum of revenue over the grouping window.", "Top-line measurement."),
    "total_cost": ("Sum of direct cost over the grouping window.", "Margin measurement."),
    "total_spend": ("Sum of marketing spend over the grouping window.", "CAC denominator input."),
    "contribution_margin": ("Revenue minus direct cost.", "Primary profitability measure."),
    "total_channel_contribution_margin": (
        "Observed contribution margin summed within an acquisition channel.",
        "Scenario baseline reconciliation.",
    ),
    "contribution_margin_pct": (
        "Contribution margin as share of revenue.",
        "Margin quality signal.",
    ),
    "contribution_margin_growth_mom": (
        "Month-over-month change in contribution margin.",
        "Margin trend monitoring.",
    ),
    "revenue_growth_mom": ("Month-over-month change in total revenue.", "Top-line momentum."),
    "cost_growth_mom": ("Month-over-month change in total cost.", "Cost trajectory."),
    "transaction_count": ("Number of transactions in the grouping.", "Volume measure."),
    "active_customers": ("Distinct customers active in the period.", "Engagement measure."),
    "customers_acquired": ("Customers whose signup falls in the period.", "CAC denominator."),
    "customers_active": (
        "Distinct cohort members with a transaction in the evaluated activity month.",
        "Signup-cohort activity numerator, including late activations.",
    ),
    "cohort_size": (
        "Distinct customers who signed up in the cohort month.",
        "Denominator for activation and signup-cohort activity rates.",
    ),
    "month_0_active_customers": (
        "Distinct cohort members with a transaction in their signup month.",
        "Fixed baseline population for retained-from-month-0 measurement.",
    ),
    "retained_month_0_customers": (
        "Month-0 active customers who also transacted in the evaluated activity month.",
        "Numerator for retained-from-month-0 activity.",
    ),
    "late_activation_customers": (
        "Active customers in the evaluated month who were not active in month 0.",
        "Separates post-signup activation from retention of the month-0 baseline.",
    ),
    "month_0_activation_rate": (
        "Month-0 active customers divided by the full signup cohort size.",
        "Acquisition-to-activation quality at cohort entry.",
    ),
    "signup_activity_rate": (
        "Customers active in the evaluated month divided by the full signup cohort size.",
        "Whole-cohort activity, including late activations and reactivations.",
    ),
    "retained_from_month_0_rate": (
        "Retained month-0 customers divided by month-0 active customers.",
        "Like-for-like retention of the activated month-0 baseline.",
    ),
    "cohort_revenue": (
        "Revenue generated by the cohort in the activity month.",
        "Cohort retention numerator.",
    ),
    "average_revenue_per_active_customer": (
        "Cohort revenue divided by active customers.",
        "Per-user revenue trajectory.",
    ),
    "avg_revenue_per_transaction": (
        "Mean transaction revenue for the customer.",
        "Ticket-size diagnostics.",
    ),
    "transaction_span_days": (
        "Inclusive days from first to last observed transaction, or zero without transactions.",
        "Descriptive transaction-window length; not customer tenure.",
    ),
    "revenue_per_transaction_span_day": (
        "Total revenue divided by inclusive observed transaction-span days.",
        "Revenue intensity within the observed transaction window.",
    ),
    "row_count": ("Number of rows in the profiled table.", "Volume reconciliation and monitoring."),
    "column_count": ("Number of columns in the profiled table.", "Schema-width monitoring."),
    "duplicate_rows": ("Count of fully duplicated rows.", "Duplicate-data quality control."),
    "duplicate_candidate_key_rows": (
        "Count of rows duplicated on the candidate primary key.",
        "Grain and uniqueness control.",
    ),
    "issue_count": ("Rows affected by the data-quality issue.", "Issue prioritization and triage."),
    "issue_rate": (
        "Affected rows divided by rows evaluated for the check.",
        "Comparable data-quality severity.",
    ),
    "touchpoint_order": (
        "One-based chronological position of a touchpoint in a customer journey.",
        "Position-based attribution weight assignment.",
    ),
    "is_conversion_touch": (
        "True for the final governed touchpoint before signup.",
        "Journey integrity and last-touch identification.",
    ),
    "assignment": (
        "Randomized control, treatment, or governed price assignment for the intervention.",
        "Causal contrast definition.",
    ),
    "outcome_window_days": (
        "Fixed post-assignment days included in experiment outcomes.",
        "Comparable treatment and control measurement.",
    ),
    "converted": (
        "Whether the assigned customer converted inside the governed outcome window.",
        "Randomized conversion-lift estimation.",
    ),
    "pre_period_contribution": (
        "Contribution observed before assignment and excluded from the outcome.",
        "CUPED variance reduction without post-treatment leakage.",
    ),
    "observed_contribution": (
        "Contribution observed inside the fixed experiment outcome window.",
        "Randomized incremental-contribution estimation.",
    ),
    "reference_price": (
        "Control price assigned to the product before the randomized multiplier.",
        "Price-index construction and intervention validation.",
    ),
    "observed_price": (
        "Price actually assigned in the randomized pricing cell.",
        "Elasticity regressor within the tested range.",
    ),
    "units_sold": (
        "Units observed in the product-region-week intervention cell.",
        "Demand outcome for elasticity estimation.",
    ),
    "control_customers": (
        "Customers assigned to the experiment control arm.",
        "Experiment balance and uncertainty assessment.",
    ),
    "treatment_customers": (
        "Customers assigned to the experiment treatment arm.",
        "Experiment balance and incremental-impact scaling.",
    ),
    "control_conversion_rate": (
        "Conversion rate in the randomized control arm.",
        "Baseline conversion performance.",
    ),
    "treatment_conversion_rate": (
        "Conversion rate in the randomized treatment arm.",
        "Treatment conversion performance.",
    ),
    "conversion_rate_lift": (
        "Treatment conversion rate minus control conversion rate.",
        "Randomized incremental conversion estimate.",
    ),
    "conversion_lift_ci_95_low": (
        "Lower bound of the 95% interval for conversion-rate lift.",
        "Uncertainty-aware experiment interpretation.",
    ),
    "conversion_lift_ci_95_high": (
        "Upper bound of the 95% interval for conversion-rate lift.",
        "Uncertainty-aware experiment interpretation.",
    ),
    "control_contribution_per_customer": (
        "CUPED-adjusted mean contribution in the control arm.",
        "Baseline experiment economics.",
    ),
    "treatment_contribution_per_customer": (
        "CUPED-adjusted mean contribution in the treatment arm.",
        "Treatment experiment economics.",
    ),
    "incremental_contribution_per_treated_customer": (
        "Adjusted treatment-minus-control contribution per treated customer.",
        "Customer-level randomized incremental value.",
    ),
    "incremental_contribution_ci_95_low": (
        "Lower 95% bound for incremental contribution per treated customer.",
        "Decision downside under experiment uncertainty.",
    ),
    "incremental_contribution_ci_95_high": (
        "Upper 95% bound for incremental contribution per treated customer.",
        "Decision upside under experiment uncertainty.",
    ),
    "incremental_contribution_total": (
        "Per-treated-customer lift multiplied by treated customers.",
        "Realized experiment-scale incremental contribution.",
    ),
    "standard_error": (
        "Estimated standard error for the primary causal contrast.",
        "Statistical uncertainty and significance assessment.",
    ),
    "p_value": (
        "Two-sided normal-approximation p-value for the primary coefficient.",
        "Evidence-strength context alongside confidence intervals.",
    ),
    "cuped_theta": (
        "Pre-period adjustment coefficient used by CUPED.",
        "Variance-reduction auditability.",
    ),
    "identification": (
        "Design that identifies the reported causal coefficient.",
        "Prevents descriptive attribution from being read as incrementality.",
    ),
    "touchpoints": (
        "Governed marketing interactions assigned to the channel.",
        "Journey-volume context for descriptive attribution.",
    ),
    "customers_reached": (
        "Distinct customers with at least one touch assigned to the channel.",
        "Descriptive channel reach.",
    ),
    "attributed_customer_equivalents": (
        "Sum of position-based fractional customer credits.",
        "Fully reconciling descriptive acquisition allocation.",
    ),
    "attributed_contribution": (
        "Observed contribution allocated by position-based journey weights.",
        "Descriptive contribution allocation across touches.",
    ),
    "attributed_contribution_share": (
        "Channel attributed contribution divided by total attributed contribution.",
        "Cross-channel descriptive allocation share.",
    ),
    "model": (
        "Named analytical model used to produce the output.",
        "Method provenance and reproducibility.",
    ),
    "claim_scope": (
        "Explicit boundary on the inference supported by the model.",
        "Guards against treating attribution as causal lift.",
    ),
    "product_scope": (
        "Product population represented by the elasticity coefficient.",
        "Global versus product-specific decision use.",
    ),
    "price_elasticity": (
        "Estimated percent change in units for a 1% price change.",
        "Observed-intervention demand response.",
    ),
    "robust_standard_error": (
        "CR1 week-clustered standard error used for elasticity inference.",
        "Pricing-coefficient uncertainty.",
    ),
    "clustered_standard_error": (
        "CR1 standard error clustered by intervention week.",
        "Primary pricing-coefficient uncertainty measure.",
    ),
    "hc1_standard_error": (
        "HC1 standard error retained as a model diagnostic.",
        "Sensitivity comparison for coefficient uncertainty.",
    ),
    "standard_error_method": (
        "Named covariance estimator used for the published interval.",
        "Inference-method provenance.",
    ),
    "clusters": (
        "Distinct intervention weeks used as covariance clusters.",
        "Cluster-count adequacy check.",
    ),
    "residual_dof": (
        "Regression observations minus estimated parameters.",
        "Model degrees-of-freedom diagnostic.",
    ),
    "condition_number": (
        "Condition number of the fitted design matrix.",
        "Numerical-stability diagnostic.",
    ),
    "sample_ratio_mismatch_p_value": (
        "Balanced-allocation sample-ratio mismatch p-value.",
        "Randomization integrity diagnostic.",
    ),
    "pre_period_standardized_mean_difference": (
        "Treatment-control standardized difference in pre-period contribution.",
        "Baseline balance diagnostic.",
    ),
    "diagnostic_status": (
        "Pass or review status for experiment integrity checks.",
        "Claim-readiness gate.",
    ),
    "payback_cac": (
        "Spend in the mature cohort acquisition window divided by mature acquired customers.",
        "Time-aligned recovery threshold for empirical payback.",
    ),
    "payback_aligned_spend": (
        "Channel spend between the first and last signup dates of the mature payback subset.",
        "Spend basis for maturity-aligned payback CAC.",
    ),
    "payback_acquisition_start": (
        "First signup date represented in the mature payback subset.",
        "Start of the payback CAC alignment window.",
    ),
    "payback_acquisition_end": (
        "Last signup date represented in the mature payback subset.",
        "End of the payback CAC alignment window.",
    ),
    "ci_95_low": (
        "Lower bound of the coefficient's 95% confidence interval.",
        "Uncertainty-aware pricing decisions.",
    ),
    "ci_95_high": (
        "Upper bound of the coefficient's 95% confidence interval.",
        "Uncertainty-aware pricing decisions.",
    ),
    "r_squared": (
        "Share of log-demand variation explained by the fitted model.",
        "Model-fit context rather than causal proof.",
    ),
    "observations": (
        "Intervention cells included in the elasticity regression.",
        "Evidence-volume context.",
    ),
    "price_variants": (
        "Distinct randomized price assignments included in the model.",
        "Identification coverage check.",
    ),
    "valid_range": (
        "Observed price-index range supporting the elasticity estimate.",
        "Prevents unsupported extrapolation.",
    ),
    "estimated_elasticity": (
        "Product elasticity used by the bounded pricing decision rule.",
        "Traceable model input for pricing recommendations.",
    ),
    "tested_price_index_min": (
        "Lowest randomized price index observed in the experiment.",
        "Recommendation lower bound.",
    ),
    "tested_price_index_max": (
        "Highest randomized price index observed in the experiment.",
        "Recommendation upper bound.",
    ),
    "recommended_price_index": (
        "In-range price multiplier maximizing predicted contribution.",
        "Bounded pricing recommendation.",
    ),
    "recommended_price": (
        "Recommended product price implied by the selected price index.",
        "Operational pricing input.",
    ),
    "predicted_weekly_units": (
        "Weekly units predicted at the recommended in-range price.",
        "Volume trade-off for the pricing decision.",
    ),
    "predicted_weekly_contribution": (
        "Weekly contribution predicted at the recommended price.",
        "Pricing objective value.",
    ),
    "predicted_weekly_contribution_uplift": (
        "Predicted contribution difference from the control price.",
        "Expected pricing decision impact.",
    ),
    "decision_rule": (
        "Documented rule selecting the recommended price candidate.",
        "Decision reproducibility and guardrails.",
    ),
    "record_count": (
        "Number of source records represented by the aggregate.",
        "Aggregate-volume context.",
    ),
    "revenue_share": (
        "Dimension revenue divided by total revenue in scope.",
        "Mix and concentration analysis.",
    ),
    "margin_pct": (
        "Contribution margin divided by revenue.",
        "Profitability quality by dimension.",
    ),
    # Unit economics
    "CAC": ("Channel marketing spend divided by customers acquired.", "Channel efficiency."),
    "LTV_to_CAC": ("Average observed LTV divided by CAC.", "Scaling guardrail."),
    "approximate_payback_period": (
        "Earliest acquisition-age month when cumulative contribution per mature customer reaches CAC.",
        "Empirical CAC recovery timing; null when maturity is insufficient or CAC is not recovered.",
    ),
    "payback_status": (
        "Payback outcome: recovered, not_recovered, or insufficient_maturity.",
        "Distinguishes observed recovery from right-censoring and unavailable evidence.",
    ),
    "payback_is_censored": (
        "True when CAC was not recovered within the governed payback horizon.",
        "Prevents a null recovery month from being interpreted as missing at random.",
    ),
    "payback_horizon_months": (
        "Latest acquisition-age month evaluated in the empirical contribution curve.",
        "Defines the recovery window and customer-maturity requirement.",
    ),
    "payback_mature_customers": (
        "Acquired customers observable through the full payback horizon, including zero-transaction customers.",
        "Denominator and evidence volume for the empirical contribution curve.",
    ),
    "payback_mature_customer_share": (
        "Payback-mature customers divided by all customers acquired in the channel.",
        "Coverage indicator for the channel payback estimate.",
    ),
    "payback_horizon_contribution_per_customer": (
        "Cumulative contribution through the payback horizon divided by mature acquired customers.",
        "Recovery evidence at the censoring boundary, including zero-transaction customers.",
    ),
    "average_LTV": ("Mean contribution margin per acquired customer.", "Value side of LTV/CAC."),
    "median_LTV": ("Median contribution margin per acquired customer.", "Skew-robust value check."),
    "baseline_spend": ("Observed channel spend before reallocation.", "Scenario budget baseline."),
    "scenario_spend": (
        "Channel spend after capped policy reallocation.",
        "Scenario allocation output.",
    ),
    "spend_change": ("Scenario spend minus baseline spend.", "Scenario allocation delta."),
    "spend_change_pct": ("Scenario spend change divided by baseline spend.", "Elasticity input."),
    "allocation_score": (
        "Non-negative observed LTV/CAC for efficient channels and zero for all other channels.",
        "Proportional weight for redistributing available scenario budget.",
    ),
    "cac_elasticity": ("Illustrative CAC response to a 1% spend change.", "Scenario assumption."),
    "ltv_elasticity": ("Illustrative LTV response to a 1% spend change.", "Scenario assumption."),
    "scenario_cac_assumed": (
        "CAC after bounded spend-response assumption.",
        "Scenario unit economics.",
    ),
    "scenario_ltv_assumed": (
        "LTV after bounded spend-response assumption.",
        "Scenario unit economics.",
    ),
    "baseline_customers_est": (
        "Customers implied by baseline spend and observed CAC.",
        "Scenario baseline volume reconciliation.",
    ),
    "scenario_customers_est": (
        "Customers implied by scenario spend and stressed CAC.",
        "Scenario volume estimate.",
    ),
    "baseline_contribution_est": (
        "Modeled contribution under the baseline allocation and observed-window economics.",
        "Scenario reconciliation baseline.",
    ),
    "scenario_contribution_est": (
        "Modeled contribution under the scenario allocation and response assumptions.",
        "Scenario outcome estimate.",
    ),
    "contribution_change_est": (
        "Scenario contribution estimate minus baseline contribution estimate.",
        "Channel-level scenario impact.",
    ),
    "estimated_contribution_uplift": (
        "Scenario contribution estimate minus the reconciled baseline.",
        "Portfolio-level scenario impact.",
    ),
    "estimated_uplift_vs_baseline": (
        "Stressed scenario contribution minus the observed baseline contribution.",
        "Stress-case downside and upside assessment.",
    ),
    "estimated_uplift_vs_base_case": (
        "Stressed scenario contribution minus the unstressed base scenario.",
        "Sensitivity relative to the modeled base case.",
    ),
    "total_budget_baseline": (
        "Total observed acquisition spend before reallocation.",
        "Budget-neutrality reconciliation.",
    ),
    "total_budget_scenario": (
        "Total acquisition spend assigned by the scenario.",
        "Budget-neutrality reconciliation.",
    ),
    "unallocated_budget": (
        "Budget held back when efficient-channel scale capacity is exhausted.",
        "Scenario allocation control.",
    ),
    "cac_multiplier": (
        "Stress-case multiplier applied to scenario CAC.",
        "Scenario sensitivity assumption.",
    ),
    "ltv_multiplier": (
        "Stress-case multiplier applied to scenario LTV.",
        "Scenario sensitivity assumption.",
    ),
    # Analytical and governance outputs
    "table_name": ("Name of the profiled source table.", "Dataset-level quality traceability."),
    "column_name": (
        "Column evaluated by the data-quality check.",
        "Field-level issue traceability.",
    ),
    "grain": ("Intended business grain of one table row.", "Key and duplicate validation."),
    "candidate_primary_key": (
        "Column or column set expected to identify the table grain.",
        "Uniqueness validation.",
    ),
    "likely_useful_dimensions": (
        "Profiled categorical fields suitable for slicing metrics.",
        "Analytical discovery and modeling.",
    ),
    "likely_useful_metrics": (
        "Profiled numeric fields suitable for aggregation.",
        "Analytical discovery and modeling.",
    ),
    "check_name": (
        "Stable identifier for a validation or quality check.",
        "Audit and failure traceability.",
    ),
    "status": ("Outcome of a validation check.", "Publication gating and triage."),
    "detail": (
        "Measured evidence produced by a validation check.",
        "Failure diagnosis and auditability.",
    ),
    "severity": ("Assigned materiality of a data-quality issue.", "Issue prioritization."),
    "description": (
        "Plain-language description of a data-quality issue.",
        "Reviewer interpretation.",
    ),
    "dimension_type": (
        "Dimension family used for the profitability aggregate.",
        "Cross-dimension comparison.",
    ),
    "dimension_value": ("Member value within the dimension family.", "Profitability drill-down."),
    "effect": ("Named component of the revenue decomposition.", "Growth-driver attribution."),
    "effect_value": (
        "Revenue change assigned to the decomposition component.",
        "Growth-driver sizing.",
    ),
    "share_of_total_change": (
        "Decomposition component divided by total revenue change.",
        "Relative growth-driver contribution.",
    ),
    "median_month_0_activation_rate": (
        "Median month-0 activation rate across cohorts mature to the evaluated age.",
        "Activation-quality benchmark with cohort maturity context.",
    ),
    "median_signup_activity_rate": (
        "Median signup activity rate across cohorts mature to the evaluated age.",
        "Whole-cohort activity benchmark by cohort age.",
    ),
    "median_retained_from_month_0_rate": (
        "Median retained-from-month-0 rate across cohorts mature to the evaluated age.",
        "Like-for-like activated-customer retention benchmark by cohort age.",
    ),
    "median_revenue_retention": (
        "Median cohort revenue ratio to month-0 revenue across eligible mature cohorts.",
        "Revenue-retention and expansion monitoring by cohort age.",
    ),
    "revenue_expansion_share_m6": (
        "Share of mature cohorts with month-six revenue above signup-month revenue.",
        "Early-life expansion assessment.",
    ),
    "efficiency_status": (
        "Channel classification under the governed LTV/CAC and payback policy.",
        "Budget-allocation guardrail.",
    ),
    "recommended_action": (
        "Policy action assigned from channel efficiency and capacity rules.",
        "Scenario decision output.",
    ),
    "scenario_name": ("Stable name of the modeled policy or stress case.", "Scenario comparison."),
    "efficient_channels_selected": (
        "Channels classified efficient and selected for scaling by the scenario policy.",
        "Scenario portfolio composition and allocation traceability.",
    ),
    "inefficient_channels_selected": (
        "Channels classified inefficient and selected for reduction by the scenario policy.",
        "Scenario portfolio risk and allocation traceability.",
    ),
    "seed": (
        "Deterministic synthetic generation seed.",
        "Scenario reproducibility and sensitivity.",
    ),
    "efficient_channels": (
        "Efficient channels identified in the seeded scenario run.",
        "Cross-seed policy stability.",
    ),
    "inefficient_channels": (
        "Inefficient channels identified in the seeded scenario run.",
        "Cross-seed risk stability.",
    ),
    "top_scale_channel": (
        "Channel receiving the largest spend increase in the seeded run.",
        "Cross-seed allocation stability.",
    ),
    "top_scale_spend_change": (
        "Spend increase assigned to the top scale channel.",
        "Cross-seed allocation magnitude.",
    ),
    "top_cut_channel": (
        "Channel receiving the largest spend reduction in the seeded run.",
        "Cross-seed allocation stability.",
    ),
    "top_cut_spend_change": (
        "Spend reduction assigned to the top cut channel.",
        "Cross-seed allocation magnitude.",
    ),
    "positive_uplift_rate": (
        "Share of synthetic seeds with positive simulated uplift.",
        "Scenario stability check.",
    ),
    "uplift_mean": (
        "Mean simulated contribution uplift across seeds.",
        "Scenario stability check.",
    ),
    "uplift_median": (
        "Median simulated contribution uplift across seeds.",
        "Scenario stability check.",
    ),
    "uplift_min": (
        "Minimum simulated contribution uplift across seeds.",
        "Scenario downside check.",
    ),
    "uplift_max": ("Maximum simulated contribution uplift across seeds.", "Scenario upside check."),
    "uplift_std": (
        "Standard deviation of simulated uplift across seeds.",
        "Scenario dispersion check.",
    ),
    "seed_count": (
        "Number of deterministic synthetic seeds in the sensitivity run.",
        "Scenario stability coverage.",
    ),
    # Findings table
    "section": ("Analysis section the finding belongs to.", "Narrative grouping."),
    "question": ("Business question the finding answers.", "Decision framing."),
    "result": ("Quantitative or qualitative result.", "Headline figure."),
    "metrics_used": ("Metrics referenced to produce the result.", "Auditability."),
    "business_interpretation": (
        "Plain-English interpretation of the result.",
        "Stakeholder communication.",
    ),
    "caveats": ("Known limitations or assumptions.", "Honest framing of confidence."),
}

LAYER_OWNER = {
    "raw": "Data Engineering",
    "processed": "Analytics Engineering",
    "output": "Analytics Lead",
}


def _infer_role(column: str, dtype: str) -> str:
    c = column.lower()
    if c.endswith("_id") or c in {"cid"}:
        return "identifier"
    if c.startswith("is_") or c.startswith("has_") or dtype == "bool":
        return "boolean"
    if "float" in dtype or "int" in dtype:
        return "metric"
    if "date" in c or c in {"month", "cohort_month", "activity_month"}:
        return "temporal"
    return "dimension"


def _validate_field_definitions(columns: set[str]) -> None:
    missing = sorted(columns - FIELD_DEFINITIONS.keys())
    blank = sorted(
        column
        for column in columns & FIELD_DEFINITIONS.keys()
        if any(not value.strip() for value in FIELD_DEFINITIONS[column])
    )
    if missing or blank:
        details = []
        if missing:
            details.append(f"missing={missing}")
        if blank:
            details.append(f"blank={blank}")
        raise ValueError("Incomplete data catalog field metadata: " + "; ".join(details))


def build_data_catalog() -> pd.DataFrame:
    missing_paths = [path for _, _, path in DATASETS if not path.exists()]
    if missing_paths:
        missing_text = ", ".join(
            str(path.relative_to(PROJECT_ROOT) if path.is_relative_to(PROJECT_ROOT) else path)
            for path in missing_paths
        )
        raise FileNotFoundError(f"Required data catalog sources are missing: {missing_text}")

    frames = [(layer, dataset, pd.read_csv(path, nrows=200)) for layer, dataset, path in DATASETS]
    _validate_field_definitions({column for _, _, frame in frames for column in frame.columns})

    rows: list[dict[str, str]] = []
    for layer, dataset, frame in frames:
        for col, dtype in frame.dtypes.items():
            definition, business_use = FIELD_DEFINITIONS[col]
            rows.append(
                {
                    "layer": layer,
                    "dataset": dataset,
                    "column": col,
                    "dtype": str(dtype),
                    "role": _infer_role(col, str(dtype)),
                    "owner": LAYER_OWNER[layer],
                    "definition": definition,
                    "business_use": business_use,
                }
            )
    return pd.DataFrame(rows).sort_values(["layer", "dataset", "column"], ignore_index=True)


def write_data_catalog_artifacts() -> None:
    OUT_TABLES_DIR.mkdir(parents=True, exist_ok=True)

    catalog = build_data_catalog()
    catalog.to_csv(OUT_TABLES_DIR / "data_catalog.csv", index=False)
