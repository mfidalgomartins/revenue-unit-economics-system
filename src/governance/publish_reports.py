"""Publish the metric registry, data catalog, and decision brief."""

from __future__ import annotations

import pandas as pd

from src.governance.data_catalog import write_data_catalog_artifacts
from src.governance.metric_registry import (
    PAYBACK_HORIZON_MONTHS,
    classify_channel_efficiency,
    write_metric_registry_report,
)
from src.paths import PROJECT_ROOT

REPORTS_DIR = PROJECT_ROOT / "outputs" / "reports"
TABLES_DIR = PROJECT_ROOT / "outputs" / "tables"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


def _format_payback(row: pd.Series) -> str:
    """Render governed payback evidence without hiding censoring."""
    status = str(row.get("payback_status", "insufficient_maturity"))
    if status == "not_recovered":
        horizon = int(row.get("payback_horizon_months", PAYBACK_HORIZON_MONTHS))
        return f">{horizon}m (not recovered)"
    if status == "insufficient_maturity" or pd.isna(row["approximate_payback_period"]):
        return "not estimable"
    return f"{float(row['approximate_payback_period']):.1f}m"


def write_decision_brief() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    monthly = pd.read_csv(TABLES_DIR / "monthly_revenue_health.csv", parse_dates=["month"])
    unit_econ = pd.read_csv(PROCESSED_DIR / "unit_economics.csv")
    scenario = pd.read_csv(TABLES_DIR / "scenario_outcomes_summary.csv")
    stress = pd.read_csv(TABLES_DIR / "scenario_stress_test_summary.csv")
    seed_sensitivity = pd.read_csv(TABLES_DIR / "scenario_seed_sensitivity_summary.csv").iloc[0]
    quality_issues = pd.read_csv(TABLES_DIR / "data_quality_issues.csv")
    incrementality = pd.read_csv(TABLES_DIR / "marketing_incrementality.csv")
    attribution = pd.read_csv(TABLES_DIR / "multi_touch_attribution.csv")
    elasticity = pd.read_csv(TABLES_DIR / "pricing_elasticity.csv")
    pricing_recommendations = pd.read_csv(TABLES_DIR / "pricing_recommendations.csv")

    total_revenue = float(monthly["total_revenue"].sum())
    total_margin = float(monthly["contribution_margin"].sum())
    margin_pct = total_margin / total_revenue if total_revenue else float("nan")

    unit_sorted = unit_econ.sort_values("LTV_to_CAC", ascending=False)
    unit_sorted = unit_sorted.assign(
        efficiency_status=unit_sorted.apply(
            lambda row: classify_channel_efficiency(
                row["LTV_to_CAC"],
                row["approximate_payback_period"],
                row.get("payback_status"),
            ),
            axis=1,
        )
    )
    top_channel = unit_sorted.iloc[0]
    bottom_channel = unit_sorted.iloc[-1]
    mature_share_min = float(unit_sorted["payback_mature_customer_share"].min())
    mature_share_max = float(unit_sorted["payback_mature_customer_share"].max())

    scenario_row = scenario.iloc[0]
    stress_by_name = stress.set_index("scenario_name")
    efficient = unit_sorted.loc[
        unit_sorted["efficiency_status"] == "efficient",
        "acquisition_channel",
    ].tolist()
    weak = unit_sorted.loc[
        unit_sorted["efficiency_status"] == "inefficient",
        "acquisition_channel",
    ].tolist()
    efficient_text = ", ".join(efficient) if efficient else "no channels"
    weak_text = ", ".join(weak) if weak else "no channels"
    negative_margin_match = quality_issues.loc[
        quality_issues["check_name"] == "cost_exceeds_revenue",
        "issue_count",
    ]
    negative_margin_rows = int(negative_margin_match.iloc[0]) if len(negative_margin_match) else 0
    experiment_lines = [
        (
            f"- {row.acquisition_channel}: ${row.incremental_contribution_per_treated_customer:,.2f} "
            f"incremental contribution per treated customer "
            f"(95% CI ${row.incremental_contribution_ci_95_low:,.2f} to "
            f"${row.incremental_contribution_ci_95_high:,.2f})"
        )
        for row in incrementality.itertuples(index=False)
    ]
    elasticity_lines = [
        (
            f"- {row.product_scope}: elasticity {row.price_elasticity:.2f} "
            f"(95% CI {row.ci_95_low:.2f} to {row.ci_95_high:.2f})"
        )
        for row in elasticity.loc[elasticity["product_scope"] != "All products"].itertuples(
            index=False
        )
    ]
    pricing_lines = [
        (
            f"- {row.product_type}: test price index {row.recommended_price_index:.2f} "
            f"(${row.recommended_price:,.2f}); predicted weekly contribution change "
            f"${row.predicted_weekly_contribution_uplift:,.2f}"
        )
        for row in pricing_recommendations.itertuples(index=False)
    ]
    attributed_total = float(attribution["attributed_contribution"].sum())

    brief_lines = [
        "# Decision Brief — Synthetic Revenue Analytics Case",
        "",
        "## Executive Summary",
        f"- Total revenue: ${total_revenue:,.2f}",
        f"- Contribution margin: ${total_margin:,.2f} ({margin_pct:.1%})",
        "- Growth quality is assessed via margin trend, cohort activation and retention, and channel unit economics.",
        "",
        "## Channel Unit Economics (Observed)",
        f"- Best channel: {top_channel['acquisition_channel']} (LTV/CAC {top_channel['LTV_to_CAC']:.2f}, payback {_format_payback(top_channel)})",
        f"- Weakest channel: {bottom_channel['acquisition_channel']} (LTV/CAC {bottom_channel['LTV_to_CAC']:.2f}, payback {_format_payback(bottom_channel)})",
        "",
        "## Randomized Incrementality Evidence",
        *experiment_lines,
        "",
        "## Observed Price Response",
        *elasticity_lines,
        "",
        "### Bounded Pricing Decisions",
        *pricing_lines,
        "",
        "## Multi-Touch Attribution (Descriptive)",
        f"- Position-based channel credits reconcile ${attributed_total:,.2f} of observed contribution.",
        "- Attribution allocates observed value across touches; randomized holdouts identify incremental impact.",
        "",
        "## Scenario Summary (Policy Simulation)",
        f"- Baseline contribution: ${scenario_row['baseline_contribution_est']:,.2f}",
        f"- Scenario contribution: ${scenario_row['scenario_contribution_est']:,.2f}",
        f"- Estimated uplift: ${scenario_row['estimated_contribution_uplift']:,.2f}",
        f"- Unallocated budget holdback: ${scenario_row['unallocated_budget']:,.2f}",
        f"- Same-process seed sensitivity: {seed_sensitivity['positive_uplift_rate']:.0%} of {int(seed_sensitivity['seed_count'])} deterministic draws produced positive modeled uplift",
        "",
        "## Stress Cases",
        f"- Best case: ${float(stress_by_name.loc['best_case', 'scenario_contribution_est']):,.2f}",
        f"- Base case: ${float(stress_by_name.loc['base_case', 'scenario_contribution_est']):,.2f}",
        f"- Worst case: ${float(stress_by_name.loc['worst_case', 'scenario_contribution_est']):,.2f}",
        "",
        "## Recommendations",
        f"1. Pilot staged reallocation toward {efficient_text}, with LTV/CAC and payback guardrails.",
        f"2. Test reductions in {weak_text} with randomized holdouts before broader cuts.",
        "3. Diagnose activation and retention separately before changing lifecycle investment.",
        "4. Use the randomized price-response estimates for bounded product tests; do not extrapolate outside the observed 0.90–1.10 index.",
        "5. Decompose remaining low-margin pockets into mix, discount, scope, and cost-to-serve before intervention.",
        "",
        "## Assumptions and Caveats",
        "- Data is synthetic and intended for methodology demonstration, not forecasting.",
        "- LTV is observed contribution margin per customer during the available window.",
        "- CAC is period-level spend divided by customers acquired in the channel.",
        f"- Payback is the first acquisition-age month when cumulative contribution per mature customer recovers CAC; unrecovered channels are right-censored at {PAYBACK_HORIZON_MONTHS} months.",
        f"- Complete payback curves use {mature_share_min:.0%} to {mature_share_max:.0%} of acquired customers by channel; younger customers are excluded from that curve only.",
        "- Scenario outputs apply illustrative, bounded CAC/LTV elasticities and cap channel-level scale-up at 100%; excess budget is held back when capacity is exhausted.",
        "- Seed sensitivity repeats the same synthetic data-generating process; it measures stability, not external validity.",
        "- Marketing lift and price elasticity use explicit randomized synthetic assignments; real deployment requires a power calculation, interference review, and external-validity check.",
        "- Multi-touch attribution is a descriptive reconciliation and is not used as a causal lift estimate.",
        f"- {negative_margin_rows:,} transactions have cost above revenue. These are retained as intentional cost-to-serve exceptions.",
    ]

    (REPORTS_DIR / "decision_brief.md").write_text(
        "\n".join(brief_lines) + "\n",
        encoding="utf-8",
    )


def run() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    write_metric_registry_report()
    write_data_catalog_artifacts()
    write_decision_brief()
    print("Supporting reports published.")
    print(f"metric_registry: {REPORTS_DIR / 'metric_registry.md'}")
    print(f"decision_brief: {REPORTS_DIR / 'decision_brief.md'}")


def main() -> None:
    run()


if __name__ == "__main__":
    main()
