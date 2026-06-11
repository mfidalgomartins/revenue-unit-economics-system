"""Publish the metric registry, data catalog, and decision brief."""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

if str(Path(__file__).resolve().parents[2]) not in sys.path:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.governance.data_catalog import write_data_catalog_artifacts
from src.governance.metric_registry import classify_channel_efficiency, write_metric_registry_report

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = PROJECT_ROOT / "outputs" / "reports"
TABLES_DIR = PROJECT_ROOT / "outputs" / "tables"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


def write_decision_brief() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    monthly = pd.read_csv(TABLES_DIR / "monthly_revenue_health.csv", parse_dates=["month"])
    findings = pd.read_csv(TABLES_DIR / "main_analysis_findings.csv")
    unit_econ = pd.read_csv(PROCESSED_DIR / "unit_economics.csv")
    scenario = pd.read_csv(TABLES_DIR / "scenario_outcomes_summary.csv")
    stress = pd.read_csv(TABLES_DIR / "scenario_stress_test_summary.csv")
    seed_sensitivity = pd.read_csv(
        TABLES_DIR / "scenario_seed_sensitivity_summary.csv"
    ).iloc[0]
    quality_issues = pd.read_csv(TABLES_DIR / "data_quality_issues.csv")

    total_revenue = float(monthly["total_revenue"].sum())
    total_cost = float(monthly["total_cost"].sum())
    total_margin = float(monthly["contribution_margin"].sum())
    margin_pct = total_margin / total_revenue if total_revenue else float("nan")

    unit_sorted = unit_econ.sort_values("LTV_to_CAC", ascending=False)
    unit_sorted = unit_sorted.assign(
        efficiency_status=unit_sorted.apply(
            lambda row: classify_channel_efficiency(
                row["LTV_to_CAC"],
                row["approximate_payback_period"],
            ),
            axis=1,
        )
    )
    top_channel = unit_sorted.iloc[0]
    bottom_channel = unit_sorted.iloc[-1]

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

    brief_lines = [
        "# Decision Brief",
        "",
        "## Executive Summary",
        f"- Total revenue: ${total_revenue:,.2f}",
        f"- Contribution margin: ${total_margin:,.2f} ({margin_pct:.1%})",
        "- Growth quality is assessed via margin trend, cohort retention, and channel unit economics.",
        "",
        "## Channel Unit Economics (Observed)",
        f"- Best channel: {top_channel['acquisition_channel']} (LTV/CAC {top_channel['LTV_to_CAC']:.2f}, payback {top_channel['approximate_payback_period']:.1f}m)",
        f"- Weakest channel: {bottom_channel['acquisition_channel']} (LTV/CAC {bottom_channel['LTV_to_CAC']:.2f}, payback {bottom_channel['approximate_payback_period']:.1f}m)",
        "",
        "## Scenario Summary (Policy Simulation)",
        f"- Baseline contribution: ${scenario_row['baseline_contribution_est']:,.2f}",
        f"- Scenario contribution: ${scenario_row['scenario_contribution_est']:,.2f}",
        f"- Estimated uplift: ${scenario_row['estimated_contribution_uplift']:,.2f}",
        f"- Unallocated budget holdback: ${scenario_row['unallocated_budget']:,.2f}",
        f"- Positive simulated uplift in same-process seed draws: {seed_sensitivity['positive_uplift_rate']:.0%} ({int(seed_sensitivity['seed_count'])} deterministic seeds)",
        "",
        "## Stress Cases",
        f"- Best case: ${float(stress_by_name.loc['best_case', 'scenario_contribution_est']):,.2f}",
        f"- Base case: ${float(stress_by_name.loc['base_case', 'scenario_contribution_est']):,.2f}",
        f"- Worst case: ${float(stress_by_name.loc['worst_case', 'scenario_contribution_est']):,.2f}",
        "",
        "## Recommendations",
        f"1. Scale {efficient_text} selectively, with LTV/CAC and payback guardrails.",
        f"2. Reduce exposure to {weak_text} until channel economics recover.",
        "3. Prioritize retention plays in cohorts with the steepest early-life decay.",
        "4. Address low-margin pockets via pricing and cost-to-serve changes.",
        "",
        "## Assumptions and Caveats",
        "- Data is synthetic and intended for methodology demonstration, not forecasting.",
        "- LTV is observed contribution margin per customer during the available window.",
        "- CAC is period-level spend divided by customers acquired in the channel.",
        "- Scenario outputs apply illustrative, bounded CAC/LTV elasticities and cap channel-level scale-up at 100%; excess budget is held back when capacity is exhausted.",
        "- Seed sensitivity repeats the same synthetic data-generating process; it measures stability, not external validity.",
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
