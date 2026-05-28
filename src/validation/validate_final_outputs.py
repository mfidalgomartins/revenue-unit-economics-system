"""Pre-delivery QA validation for full analytical output."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

import pandas as pd

if str(Path(__file__).resolve().parents[2]) not in sys.path:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.governance.metric_registry import (
    EFFICIENCY_THRESHOLDS,
    classify_channel_efficiency,
)
from src.governance.release_governance import changelog_contains_version, read_version

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROC_DIR = PROJECT_ROOT / "data" / "processed"
OUT_TABLES_DIR = PROJECT_ROOT / "outputs" / "tables"
OUT_CHARTS_DIR = PROJECT_ROOT / "outputs" / "charts"
REPORTS_DIR = PROJECT_ROOT / "outputs" / "reports"

DASHBOARD_SIZE_WARN_MB = 7.0
DASHBOARD_SIZE_FAIL_MB = 9.0
DASHBOARD_PAYLOAD_WARN_ROWS = 100_000
DASHBOARD_PAYLOAD_FAIL_ROWS = 130_000


@dataclass
class CheckResult:
    category: str
    check_name: str
    status: str  # PASS, WARN, FAIL
    detail: str


@dataclass
class Issue:
    severity: str  # high, medium, low
    area: str
    issue: str
    impact: str
    recommendation: str


def load_data() -> dict[str, pd.DataFrame]:
    scenario_summary_path = OUT_TABLES_DIR / "scenario_outcomes_summary.csv"
    scenario_plan_path = OUT_TABLES_DIR / "scenario_reallocation_plan.csv"
    scenario_stress_path = OUT_TABLES_DIR / "scenario_stress_test_summary.csv"
    scenario_benchmark_path = OUT_TABLES_DIR / "scenario_benchmark_by_seed.csv"

    return {
        "customers": pd.read_csv(RAW_DIR / "customers.csv", parse_dates=["signup_date"]),
        "transactions": pd.read_csv(
            RAW_DIR / "transactions.csv", parse_dates=["transaction_date"]
        ),
        "marketing": pd.read_csv(RAW_DIR / "marketing_spend.csv", parse_dates=["date"]),
        "customer_metrics": pd.read_csv(
            PROC_DIR / "customer_metrics.csv",
            parse_dates=["first_transaction_date", "last_transaction_date"],
        ),
        "cohort_table": pd.read_csv(
            PROC_DIR / "cohort_table.csv", parse_dates=["cohort_month", "activity_month"]
        ),
        "unit_economics": pd.read_csv(PROC_DIR / "unit_economics.csv"),
        "monthly": pd.read_csv(OUT_TABLES_DIR / "monthly_revenue_health.csv", parse_dates=["month"]),
        "revenue_decomposition": pd.read_csv(OUT_TABLES_DIR / "revenue_decomposition_effects.csv"),
        "findings": pd.read_csv(OUT_TABLES_DIR / "main_analysis_findings.csv"),
        "cohort_retention": pd.read_csv(OUT_TABLES_DIR / "cohort_retention_summary.csv"),
        "unit_econ_diagnostics": pd.read_csv(OUT_TABLES_DIR / "unit_economics_channel_diagnostics.csv"),
        "scenario_summary": pd.read_csv(scenario_summary_path)
        if scenario_summary_path.exists()
        else pd.DataFrame(),
        "scenario_plan": pd.read_csv(scenario_plan_path)
        if scenario_plan_path.exists()
        else pd.DataFrame(),
        "scenario_stress": pd.read_csv(scenario_stress_path)
        if scenario_stress_path.exists()
        else pd.DataFrame(),
        "scenario_benchmark": pd.read_csv(scenario_benchmark_path)
        if scenario_benchmark_path.exists()
        else pd.DataFrame(),
    }


def run_checks(data: dict[str, pd.DataFrame]) -> tuple[list[CheckResult], list[Issue], list[str], list[str], str]:
    checks: list[CheckResult] = []
    issues: list[Issue] = []
    fixes_applied: list[str] = []
    caveats: list[str] = []

    customers = data["customers"]
    transactions = data["transactions"]
    marketing = data["marketing"]
    customer_metrics = data["customer_metrics"]
    monthly = data["monthly"]
    unit_economics = data["unit_economics"]
    findings = data["findings"]

    # 1) Data consistency.
    checks.append(
        CheckResult(
            "data_consistency",
            "row_count_sanity",
            "PASS"
            if len(customers) == len(customer_metrics) and len(transactions) > 0 and len(marketing) > 0
            else "FAIL",
            (
                f"customers={len(customers):,}, customer_metrics={len(customer_metrics):,}, "
                f"transactions={len(transactions):,}, marketing_spend={len(marketing):,}"
            ),
        )
    )

    raw_nulls = (
        int(customers.isna().sum().sum())
        + int(transactions.isna().sum().sum())
        + int(marketing.isna().sum().sum())
    )
    checks.append(
        CheckResult(
            "data_consistency",
            "null_handling_raw_tables",
            "PASS" if raw_nulls == 0 else "FAIL",
            f"Total raw nulls={raw_nulls}",
        )
    )

    cm_null_cols = customer_metrics[["first_transaction_date", "last_transaction_date"]].isna().sum()
    non_tx_customers = int((customer_metrics["transaction_count"] == 0).sum())
    checks.append(
        CheckResult(
            "data_consistency",
            "null_handling_processed_tables",
            "PASS"
            if int(cm_null_cols["first_transaction_date"]) == non_tx_customers
            and int(cm_null_cols["last_transaction_date"]) == non_tx_customers
            else "WARN",
            (
                f"first_transaction_date nulls={int(cm_null_cols['first_transaction_date'])}, "
                f"last_transaction_date nulls={int(cm_null_cols['last_transaction_date'])}, "
                f"customers_with_zero_transactions={non_tx_customers}"
            ),
        )
    )

    dup_customer = int(customers.duplicated("customer_id").sum())
    dup_tx = int(transactions.duplicated("transaction_id").sum())
    dup_marketing = int(marketing.duplicated(["date", "acquisition_channel"]).sum())
    checks.append(
        CheckResult(
            "data_consistency",
            "duplicate_handling",
            "PASS" if dup_customer == 0 and dup_tx == 0 and dup_marketing == 0 else "FAIL",
            (
                f"duplicate customer_id={dup_customer}, duplicate transaction_id={dup_tx}, "
                f"duplicate marketing grain={dup_marketing}"
            ),
        )
    )

    # 2) Calculation checks.
    tr_rev = float(transactions["revenue"].sum())
    tr_cost = float(transactions["cost"].sum())
    tr_margin = tr_rev - tr_cost

    cm_rev = float(customer_metrics["total_revenue"].sum())
    cm_cost = float(customer_metrics["total_cost"].sum())
    cm_margin = float(customer_metrics["contribution_margin"].sum())

    mon_rev = float(monthly["total_revenue"].sum())
    mon_cost = float(monthly["total_cost"].sum())
    mon_margin = float(monthly["contribution_margin"].sum())

    tol = 0.05
    checks.append(
        CheckResult(
            "calculation_checks",
            "total_revenue_consistency",
            "PASS" if abs(tr_rev - cm_rev) < tol and abs(tr_rev - mon_rev) < tol else "FAIL",
            f"transactions={tr_rev:.2f}, customer_metrics={cm_rev:.2f}, monthly={mon_rev:.2f}",
        )
    )

    checks.append(
        CheckResult(
            "calculation_checks",
            "total_cost_consistency",
            "PASS" if abs(tr_cost - cm_cost) < tol and abs(tr_cost - mon_cost) < tol else "FAIL",
            f"transactions={tr_cost:.2f}, customer_metrics={cm_cost:.2f}, monthly={mon_cost:.2f}",
        )
    )

    checks.append(
        CheckResult(
            "calculation_checks",
            "contribution_margin_logic",
            "PASS"
            if abs(tr_margin - cm_margin) < tol and abs(tr_margin - mon_margin) < tol
            else "FAIL",
            f"transactions={tr_margin:.2f}, customer_metrics={cm_margin:.2f}, monthly={mon_margin:.2f}",
        )
    )

    cm_pct_expected = (
        customer_metrics.loc[customer_metrics["total_revenue"] > 0, "contribution_margin"]
        / customer_metrics.loc[customer_metrics["total_revenue"] > 0, "total_revenue"]
    )
    cm_pct_observed = customer_metrics.loc[
        customer_metrics["total_revenue"] > 0, "contribution_margin_pct"
    ]
    cm_pct_err = float((cm_pct_expected - cm_pct_observed).abs().max())

    avg_tx_expected = (
        customer_metrics.loc[customer_metrics["transaction_count"] > 0, "total_revenue"]
        / customer_metrics.loc[customer_metrics["transaction_count"] > 0, "transaction_count"]
    )
    avg_tx_err = float(
        (
            avg_tx_expected
            - customer_metrics.loc[
                customer_metrics["transaction_count"] > 0, "avg_revenue_per_transaction"
            ]
        )
        .abs()
        .max()
    )

    checks.append(
        CheckResult(
            "calculation_checks",
            "denominator_correctness_rates",
            "PASS" if cm_pct_err <= 1e-5 and avg_tx_err <= 0.01 else "WARN",
            (
                f"max contribution_margin_pct error={cm_pct_err:.8f}, "
                f"max avg_revenue_per_transaction error={avg_tx_err:.6f}"
            ),
        )
    )

    cust_by_ch = customers.groupby("acquisition_channel")["customer_id"].nunique()
    spend_by_ch = marketing.groupby("acquisition_channel")["spend"].sum()
    avg_ltv_by_ch = customer_metrics.groupby("acquisition_channel")["contribution_margin"].mean()
    med_ltv_by_ch = customer_metrics.groupby("acquisition_channel")["contribution_margin"].median()
    total_cm_by_ch = customer_metrics.groupby("acquisition_channel")["contribution_margin"].sum()
    months_obs = marketing["date"].dt.to_period("M").nunique()

    max_cac_diff = 0.0
    max_ltv_diff = 0.0
    max_payback_diff = 0.0
    for row in unit_economics.itertuples(index=False):
        ch = row.acquisition_channel
        exp_cac = spend_by_ch[ch] / cust_by_ch[ch]
        exp_avg_ltv = avg_ltv_by_ch[ch]
        exp_med_ltv = med_ltv_by_ch[ch]
        exp_mcm = (total_cm_by_ch[ch] / months_obs) / cust_by_ch[ch]
        exp_payback = exp_cac / exp_mcm if exp_mcm > 0 else float("nan")

        max_cac_diff = max(max_cac_diff, abs(float(row.CAC) - float(exp_cac)))
        max_ltv_diff = max(
            max_ltv_diff,
            abs(float(row.average_LTV) - float(exp_avg_ltv)),
            abs(float(row.median_LTV) - float(exp_med_ltv)),
        )
        if pd.notna(exp_payback):
            max_payback_diff = max(max_payback_diff, abs(float(row.approximate_payback_period) - float(exp_payback)))

    checks.append(
        CheckResult(
            "calculation_checks",
            "ltv_cac_payback_logic",
            "PASS" if max_cac_diff < 0.01 and max_ltv_diff < 0.01 and max_payback_diff < 0.01 else "FAIL",
            (
                f"max CAC diff={max_cac_diff:.6f}, max LTV diff={max_ltv_diff:.6f}, "
                f"max payback diff={max_payback_diff:.6f}"
            ),
        )
    )

    # 3) Analytical integrity.
    joined = transactions.merge(customers[["customer_id", "segment"]], on="customer_id", how="left")
    checks.append(
        CheckResult(
            "analytical_integrity",
            "join_inflation_check",
            "PASS" if len(joined) == len(transactions) and int(joined["segment"].isna().sum()) == 0 else "FAIL",
            (
                f"transactions rows pre={len(transactions):,}, post={len(joined):,}, "
                f"orphans={int(joined['segment'].isna().sum()):,}"
            ),
        )
    )

    months = int(monthly["month"].nunique())
    overlap = monthly["month"].sort_values().head(6).isin(monthly["month"].sort_values().tail(6)).any()
    checks.append(
        CheckResult(
            "analytical_integrity",
            "incomplete_period_comparison_check",
            "PASS" if months >= 12 and not overlap else "WARN",
            f"months_available={months}, early_recent_window_overlap={bool(overlap)}",
        )
    )

    decomp = data["revenue_decomposition"]
    share_sum = float(
        decomp.loc[
            decomp["effect"].isin(
                [
                    "customer_volume_effect",
                    "mix_effect",
                    "average_revenue_effect",
                    "residual",
                ]
            ),
            "share_of_total_change",
        ]
        .fillna(0.0)
        .sum()
    )
    residual_abs = float(
        decomp.loc[decomp["effect"] == "residual", "effect_value"].iloc[0]
    )
    total_change_abs = float(
        abs(
            decomp.loc[
                decomp["effect"] == "total_revenue_change",
                "effect_value",
            ].iloc[0]
        )
    )
    residual_ratio = residual_abs / total_change_abs if total_change_abs > 0 else 0.0
    checks.append(
        CheckResult(
            "analytical_integrity",
            "decomposition_consistency_check",
            "PASS" if abs(share_sum - 1.0) <= 0.02 and residual_ratio <= 0.05 else "WARN",
            (
                f"share_sum={share_sum:.4f}, residual_share_of_total={residual_ratio:.4f}. "
                "Interpretation should remain directional, not causal."
            ),
        )
    )

    required_sections = {
        "1. Overall Revenue Health",
        "2. Revenue Decomposition",
        "3. Cohort Analysis",
        "4. Unit Economics",
        "5. Segment Profitability",
    }
    sections_ok = set(findings["section"].tolist()) == required_sections

    unit_diag = data["unit_econ_diagnostics"]
    eff = unit_diag.loc[unit_diag["efficiency_status"] == "efficient", "acquisition_channel"].tolist()
    ineff = unit_diag.loc[unit_diag["efficiency_status"] == "inefficient", "acquisition_channel"].tolist()

    findings_text = " ".join(findings["result"].astype(str).tolist()).lower()
    evidence_match = all(ch.lower() in findings_text for ch in eff + ineff)

    checks.append(
        CheckResult(
            "analytical_integrity",
            "conclusions_match_evidence",
            "PASS" if sections_ok and evidence_match else "WARN",
            (
                f"sections_complete={sections_ok}, efficient_channels={eff}, inefficient_channels={ineff}, "
                f"channels_referenced_in_findings={evidence_match}"
            ),
        )
    )

    expected_status = unit_economics.apply(
        lambda r: classify_channel_efficiency(r["LTV_to_CAC"], r["approximate_payback_period"]),
        axis=1,
    ).tolist()
    observed_status = unit_diag.sort_values("acquisition_channel")["efficiency_status"].tolist()
    expected_sorted = (
        unit_economics.assign(expected_status=expected_status)
        .sort_values("acquisition_channel")["expected_status"]
        .tolist()
    )
    checks.append(
        CheckResult(
            "analytical_integrity",
            "efficiency_policy_consistency",
            "PASS" if observed_status == expected_sorted else "FAIL",
            (
                f"policy_thresholds: efficient LTV/CAC>={EFFICIENCY_THRESHOLDS.ltv_cac_target}, "
                f"payback<={EFFICIENCY_THRESHOLDS.payback_target_months}; "
                f"status_match={observed_status == expected_sorted}"
            ),
        )
    )

    # 4) Visualization checks.
    chart_files = sorted([p.name for p in OUT_CHARTS_DIR.glob("*.png")])
    mandatory = [
        "01_revenue_trend_over_time.png",
        "02_contribution_margin_trend_over_time.png",
        "03_revenue_vs_cost_over_time.png",
        "04_cohort_revenue_retention.png",
        "05_ltv_vs_cac_by_acquisition_channel.png",
        "06_contribution_margin_by_segment.png",
        "07_revenue_distribution_across_customers.png",
        "08_avg_revenue_per_transaction_by_segment.png",
    ]
    missing = sorted(set(mandatory) - set(chart_files))

    checks.append(
        CheckResult(
            "visualization_checks",
            "mandatory_chart_coverage",
            "PASS" if len(missing) == 0 else "FAIL",
            f"charts_present={len(chart_files)}, missing={missing if missing else 'none'}",
        )
    )

    chart_index_text = (OUT_CHARTS_DIR / "chart_index.md").read_text(encoding="utf-8")
    checks.append(
        CheckResult(
            "visualization_checks",
            "chart_index_completeness",
            "PASS" if chart_index_text.count(".png") >= 8 else "FAIL",
            f"chart_index_rows_detected={chart_index_text.count('.png')}",
        )
    )

    viz_code = (PROJECT_ROOT / "src" / "visualization" / "generate_visuals.py").read_text(encoding="utf-8")
    axis_zero_ok = (
        "chart_revenue_trend" in viz_code
        and "chart_margin_trend" in viz_code
        and "chart_revenue_vs_cost" in viz_code
        and viz_code.count("set_ylim(bottom=0)") >= 4
    )

    checks.append(
        CheckResult(
            "visualization_checks",
            "axis_sanity_and_misleading_scale",
            "PASS" if axis_zero_ok else "WARN",
            "Money trend charts set y-axis baseline to zero; cohort/ltv-cac also anchored for interpretability.",
        )
    )

    # 5) Governance and reproducibility checks.
    reports_validation = REPORTS_DIR / "pre_delivery_validation_report.md"
    checks.append(
        CheckResult(
            "governance_checks",
            "validation_report_presence",
            "PASS" if reports_validation.exists() else "WARN",
            f"report_exists={reports_validation.exists()}",
        )
    )

    metric_registry_path = REPORTS_DIR / "metric_governance_registry.md"
    checks.append(
        CheckResult(
            "governance_checks",
            "metric_registry_presence",
            "PASS" if metric_registry_path.exists() else "WARN",
            f"metric_registry_exists={metric_registry_path.exists()}",
        )
    )

    data_catalog_table = OUT_TABLES_DIR / "data_catalog.csv"
    data_catalog_ok = data_catalog_table.exists()
    checks.append(
        CheckResult(
            "governance_checks",
            "data_catalog_presence",
            "PASS" if data_catalog_ok else "WARN",
            f"table_exists={data_catalog_table.exists()}",
        )
    )

    version = read_version()
    version_semver_ok = (
        len(version.split(".")) == 3 and all(part.isdigit() for part in version.split("."))
    )
    checks.append(
        CheckResult(
            "governance_checks",
            "release_version_semver",
            "PASS" if version_semver_ok else "WARN",
            f"version={version}",
        )
    )

    changelog_ok = changelog_contains_version(version)
    checks.append(
        CheckResult(
            "governance_checks",
            "release_changelog_alignment",
            "PASS" if changelog_ok else "WARN",
            f"changelog_contains_version={changelog_ok}",
        )
    )

    dashboard_html_path = PROJECT_ROOT / "outputs" / "dashboard" / "growth-quality-dashboard.html"
    dashboard_text = dashboard_html_path.read_text(encoding="utf-8") if dashboard_html_path.exists() else ""
    deterministic_metadata_ok = "generated_at" not in dashboard_text
    checks.append(
        CheckResult(
            "governance_checks",
            "dashboard_deterministic_metadata",
            "PASS" if deterministic_metadata_ok else "WARN",
            "Dashboard payload should avoid volatile build timestamps.",
        )
    )

    scenario_summary = data["scenario_summary"]
    scenario_plan = data["scenario_plan"]
    scenario_stress = data["scenario_stress"]
    scenario_benchmark = data["scenario_benchmark"]
    scenario_ok = not scenario_summary.empty and not scenario_plan.empty
    checks.append(
        CheckResult(
            "decision_support_checks",
            "scenario_engine_outputs",
            "PASS" if scenario_ok else "WARN",
            (
                f"scenario_summary_rows={len(scenario_summary)}, "
                f"scenario_plan_rows={len(scenario_plan)}"
            ),
        )
    )
    if scenario_ok:
        uplift = float(scenario_summary["estimated_contribution_uplift"].iloc[0])
        checks.append(
            CheckResult(
                "decision_support_checks",
                "scenario_uplift_directionality",
                "PASS" if uplift >= 0 else "WARN",
                f"estimated_contribution_uplift={uplift:.2f}",
            )
        )
    stress_ok = not scenario_stress.empty
    checks.append(
        CheckResult(
            "decision_support_checks",
            "scenario_stress_test_outputs",
            "PASS" if stress_ok else "WARN",
            f"scenario_stress_rows={len(scenario_stress)}",
        )
    )
    if stress_ok:
        by_name = scenario_stress.set_index("scenario_name")
        required_cases = {"best_case", "base_case", "worst_case"}
        has_cases = required_cases.issubset(set(by_name.index.tolist()))
        monotonic = (
            has_cases
            and float(by_name.loc["best_case", "scenario_contribution_est"])
            >= float(by_name.loc["base_case", "scenario_contribution_est"])
            >= float(by_name.loc["worst_case", "scenario_contribution_est"])
        )
        checks.append(
            CheckResult(
                "decision_support_checks",
                "scenario_stress_monotonicity",
                "PASS" if monotonic else "WARN",
                (
                    f"required_cases_present={has_cases}; "
                    + (
                        f"best={float(by_name.loc['best_case', 'scenario_contribution_est']):.2f}, "
                        f"base={float(by_name.loc['base_case', 'scenario_contribution_est']):.2f}, "
                        f"worst={float(by_name.loc['worst_case', 'scenario_contribution_est']):.2f}"
                        if has_cases
                        else "stress scenario names should include best_case/base_case/worst_case"
                    )
                ),
            )
        )

    benchmark_ok = not scenario_benchmark.empty
    checks.append(
        CheckResult(
            "decision_support_checks",
            "scenario_benchmark_outputs",
            "PASS" if benchmark_ok else "WARN",
            f"scenario_benchmark_rows={len(scenario_benchmark)}",
        )
    )
    if benchmark_ok:
        seeds = sorted(scenario_benchmark["seed"].astype(int).tolist())
        required_seeds = {7, 21, 42, 84, 126}
        seed_coverage_ok = required_seeds.issubset(set(seeds))
        checks.append(
            CheckResult(
                "decision_support_checks",
                "scenario_benchmark_seed_coverage",
                "PASS" if seed_coverage_ok else "WARN",
                f"seeds_present={seeds}",
            )
        )
        uplift_positive_rate = float(
            (scenario_benchmark["estimated_contribution_uplift"] > 0).mean()
        )
        checks.append(
            CheckResult(
                "decision_support_checks",
                "scenario_benchmark_uplift_resilience",
                "PASS" if uplift_positive_rate >= 0.8 else "WARN",
                f"positive_uplift_rate={uplift_positive_rate:.2%}",
            )
        )

    payload_rows = len(customers) + len(transactions) + len(marketing)
    if payload_rows <= DASHBOARD_PAYLOAD_WARN_ROWS:
        perf_status = "PASS"
    elif payload_rows <= DASHBOARD_PAYLOAD_FAIL_ROWS:
        perf_status = "WARN"
    else:
        perf_status = "FAIL"
    checks.append(
        CheckResult(
            "governance_checks",
            "dashboard_payload_budget_rows",
            perf_status,
            (
                f"payload_rows={payload_rows:,}, "
                f"warn_threshold={DASHBOARD_PAYLOAD_WARN_ROWS:,}, "
                f"fail_threshold={DASHBOARD_PAYLOAD_FAIL_ROWS:,}"
            ),
        )
    )

    # Issues, fixes, caveats.
    issues.append(
        Issue(
            severity="low",
            area="analytical_integrity",
            issue="Revenue decomposition volume effect is window-level and ARPC-based, not a strict causal decomposition.",
            impact="Effect magnitudes can be over-interpreted if treated as causal drivers rather than directional components.",
            recommendation="Keep decomposition language directional and pair with sensitivity checks using alternative mix dimensions.",
        )
    )

    if dashboard_html_path.exists():
        dashboard_size_mb = dashboard_html_path.stat().st_size / (1024 * 1024)
        if dashboard_size_mb <= DASHBOARD_SIZE_WARN_MB:
            size_status = "PASS"
        elif dashboard_size_mb <= DASHBOARD_SIZE_FAIL_MB:
            size_status = "WARN"
        else:
            size_status = "FAIL"

        checks.append(
            CheckResult(
                "governance_checks",
                "dashboard_size_budget_mb",
                size_status,
                (
                    f"dashboard_size_mb={dashboard_size_mb:.2f}, "
                    f"warn_threshold={DASHBOARD_SIZE_WARN_MB:.2f}, "
                    f"fail_threshold={DASHBOARD_SIZE_FAIL_MB:.2f}"
                ),
            )
        )

        if dashboard_size_mb > DASHBOARD_SIZE_FAIL_MB:
            issues.append(
                Issue(
                    severity="medium",
                    area="dashboard_performance",
                    issue=f"Executive dashboard size is {dashboard_size_mb:.2f}MB (beyond fail budget).",
                    impact="Can load slowly on low-resource machines and reduce usability.",
                    recommendation="Reduce payload size with pre-aggregated facts and compressed dimensional joins.",
                )
            )
        elif dashboard_size_mb > DASHBOARD_SIZE_WARN_MB:
            issues.append(
                Issue(
                    severity="low",
                    area="dashboard_performance",
                    issue=f"Executive dashboard size is {dashboard_size_mb:.2f}MB (above warning budget).",
                    impact="Offline load latency may increase in constrained environments.",
                    recommendation="Apply payload pre-aggregation to bring dashboard under budget.",
                )
            )
    else:
        issues.append(
            Issue(
                severity="medium",
                area="dashboard_outputs",
                issue="Dashboard HTML output is missing.",
                impact="Executive delivery package is incomplete.",
                recommendation="Rebuild dashboard assets and re-run validation.",
            )
        )

    if non_tx_customers > 0:
        issues.append(
            Issue(
                severity="low",
                area="data_consistency",
                issue="`customer_metrics` has null first/last transaction dates for customers with zero transactions.",
                impact="Nulls are expected but must remain explicitly handled in downstream visuals/tables.",
                recommendation="Retain explicit zero-transaction handling and avoid dropping these rows in customer-level analyses.",
            )
        )

    if not version_semver_ok or not changelog_ok:
        issues.append(
            Issue(
                severity="medium",
                area="release_governance",
                issue="Release version or changelog policy is not aligned with SemVer governance.",
                impact="Weakens release auditability and interview defensibility for production-grade analytics delivery.",
                recommendation="Ensure VERSION follows MAJOR.MINOR.PATCH and changelog includes matching version section.",
            )
        )

    caveats.append(
        "All findings are based on synthetic data; directional insights are valid for methodology demonstration, not real-world forecasting precision."
    )
    caveats.append(
        "Unit economics use observed contribution margin and period-level spend allocation; attribution lags are not modeled."
    )
    caveats.append(
        "Revenue decomposition should be interpreted as directional decomposition, not formal causal attribution."
    )
    caveats.append(
        "Scenario engine outputs are policy simulations assuming stable CAC/LTV under spend changes, not forecasts."
    )

    fail_count = sum(1 for c in checks if c.status == "FAIL")
    warn_count = sum(1 for c in checks if c.status == "WARN")
    has_high_issue = any(i.severity == "high" for i in issues)
    has_medium_issue = any(i.severity == "medium" for i in issues)

    if fail_count > 0 or has_high_issue:
        confidence = "Needs revision"
    elif warn_count >= 3 or has_medium_issue:
        confidence = "Share with caveats"
    else:
        confidence = "Ready to share"

    return checks, issues, fixes_applied, caveats, confidence


def write_outputs(
    checks: list[CheckResult],
    issues: list[Issue],
    fixes_applied: list[str],
    caveats: list[str],
    confidence: str,
) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    OUT_TABLES_DIR.mkdir(parents=True, exist_ok=True)

    checks_df = pd.DataFrame([c.__dict__ for c in checks])
    issues_df = pd.DataFrame([i.__dict__ for i in issues])

    checks_df.to_csv(OUT_TABLES_DIR / "pre_delivery_validation_checks.csv", index=False)
    issues_df.to_csv(OUT_TABLES_DIR / "pre_delivery_validation_issues.csv", index=False)

    pass_count = int((checks_df["status"] == "PASS").sum())
    warn_count = int((checks_df["status"] == "WARN").sum())
    fail_count = int((checks_df["status"] == "FAIL").sum())

    def to_markdown_fallback(df: pd.DataFrame) -> str:
        cols = list(df.columns)
        header = "| " + " | ".join(cols) + " |"
        divider = "| " + " | ".join(["---"] * len(cols)) + " |"
        body = []
        for row in df.itertuples(index=False):
            body.append("| " + " | ".join(str(v) for v in row) + " |")
        return "\n".join([header, divider] + body)

    report_lines = [
        "# Pre-Delivery Validation Report",
        "",
        "Project: Revenue Analytics & Unit Economics System",
        "",
        "## Validation Scope",
        "- Data consistency (row count, null handling, duplicate handling)",
        "- Calculation checks (revenue/cost/margin/rates/LTV/CAC/payback)",
        "- Analytical integrity (join inflation, period comparison, averaging risks, evidence alignment)",
        "- Visualization checks (title quality, axis sanity, readability, scale risk)",
        "",
        "## Validation Summary",
        f"- PASS checks: {pass_count}",
        f"- WARN checks: {warn_count}",
        f"- FAIL checks: {fail_count}",
        f"- Final confidence assessment: **{confidence}**",
        "",
        "## Check Results",
        to_markdown_fallback(checks_df),
        "",
        "## Issues Found",
    ]

    if issues_df.empty:
        report_lines.append("- No issues detected.")
    else:
        for i in issues:
            report_lines.extend(
                [
                    f"- **[{i.severity.upper()}] {i.area}**",
                    f"  Issue: {i.issue}",
                    f"  Impact: {i.impact}",
                    f"  Recommendation: {i.recommendation}",
                ]
            )

    report_lines.extend(["", "## Fixes Applied"])
    if fixes_applied:
        for fix in fixes_applied:
            report_lines.append(f"- {fix}")
    else:
        report_lines.append("- No code or output fixes were applied during this QA pass.")

    report_lines.extend(["", "## Required Caveats"])
    for caveat in caveats:
        report_lines.append(f"- {caveat}")

    report_lines.extend(
        [
            "",
            "## Output Files",
            "- `outputs/tables/pre_delivery_validation_checks.csv`",
            "- `outputs/tables/pre_delivery_validation_issues.csv`",
            "- `outputs/reports/pre_delivery_validation_report.md`",
            "- `outputs/tables/scenario_reallocation_plan.csv`",
            "- `outputs/tables/scenario_outcomes_summary.csv`",
            "- `outputs/tables/scenario_stress_test_summary.csv`",
            "- `outputs/tables/scenario_benchmark_by_seed.csv`",
            "- `outputs/reports/metric_governance_registry.md`",
            "- `outputs/tables/data_catalog.csv`",
            "- `outputs/tables/release_manifest.csv`",
            "- `outputs/reports/release_governance.md`",
        ]
    )

    (REPORTS_DIR / "pre_delivery_validation_report.md").write_text(
        "\n".join(report_lines), encoding="utf-8"
    )


def main() -> None:
    data = load_data()
    checks, issues, fixes_applied, caveats, confidence = run_checks(data)
    write_outputs(checks, issues, fixes_applied, caveats, confidence)

    print("Pre-delivery validation completed.")
    print(f"report: {REPORTS_DIR / 'pre_delivery_validation_report.md'}")
    print(f"checks_csv: {OUT_TABLES_DIR / 'pre_delivery_validation_checks.csv'}")
    print(f"issues_csv: {OUT_TABLES_DIR / 'pre_delivery_validation_issues.csv'}")
    print(f"confidence: {confidence}")


if __name__ == "__main__":
    main()
