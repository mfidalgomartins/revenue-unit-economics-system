"""Run the final QA gate for analytical outputs."""

from __future__ import annotations

import json
import math
import re
import struct
from dataclasses import dataclass
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from pypdf import PdfReader

from src.api.service import AggregateDashboardService, DashboardFilters
from src.data_contracts import ACQUISITION_CHANNELS, PRODUCT_TYPES, REGIONS, SEGMENTS
from src.feature_engineering.build_features import build_unit_economics
from src.governance.metric_registry import (
    EFFICIENCY_THRESHOLDS,
    classify_channel_efficiency,
)
from src.paths import PROJECT_ROOT, RAW_DATA_DIR
from src.scenario_engine.build_scenarios import MAX_SCALE_UPLIFT
from src.visualization.chart_manifest import expected_chart_files

RAW_DIR = RAW_DATA_DIR
PROC_DIR = PROJECT_ROOT / "data" / "processed"
OUT_TABLES_DIR = PROJECT_ROOT / "outputs" / "tables"
OUT_CHARTS_DIR = PROJECT_ROOT / "outputs" / "charts"
REPORTS_DIR = PROJECT_ROOT / "outputs" / "reports"
WAREHOUSE_PATH = PROJECT_ROOT / "outputs" / "duckdb" / "revenue_analytics.duckdb"
GOVERNANCE_DIR = PROJECT_ROOT / "outputs" / "governance"

DASHBOARD_SIZE_WARN_MB = 7.0
DASHBOARD_SIZE_FAIL_MB = 9.0
DASHBOARD_PAYLOAD_WARN_ROWS = 100_000
DASHBOARD_PAYLOAD_FAIL_ROWS = 130_000
GATE_FAILED = "Analytical consistency gate failed"
GATE_PASSED_WITH_CAVEATS = "Analytical consistency gate passed with caveats"
GATE_PASSED = "Analytical consistency gate passed"


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


def read_png_dimensions(path: Path) -> tuple[int, int]:
    """Return PNG height and width without importing an image library."""
    with path.open("rb") as image_file:
        header = image_file.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"Invalid PNG header: {path}")
    width, height = struct.unpack(">II", header[16:24])
    return height, width


def inspect_analytical_pdf(path: Path) -> tuple[bool, str]:
    """Validate that the published PDF is parseable, navigable, and self-describing."""
    if not path.exists():
        return False, "report_missing"
    try:
        reader = PdfReader(path, strict=True)
        page_count = len(reader.pages)
        metadata = dict(reader.metadata or {})
        root = reader.root_object
        language = str(root.get("/Lang", ""))
        tagged = "/StructTreeRoot" in root
        outline_count = len(reader.outline)
        extracted_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        return False, f"parse_error={type(exc).__name__}: {exc}"

    required_markers = {
        "Executive summary",
        "Data and methodology",
        "The data is synthetic",
        "Recommendations and action priorities",
    }
    missing_markers = sorted(marker for marker in required_markers if marker not in extracted_text)
    volatile_metadata = sorted(key for key in ("/CreationDate", "/ModDate") if key in metadata)
    expected_title = "Revenue Analytics and Unit Economics — Synthetic Case Study"
    page_count_in_range = 10 <= page_count <= 60
    metadata_valid = metadata.get("/Title") == expected_title and bool(metadata.get("/Author"))
    language_valid = language == "en-US"
    outline_valid = outline_count >= 9
    valid = (
        page_count_in_range
        and metadata_valid
        and language_valid
        and tagged
        and outline_valid
        and not missing_markers
        and not volatile_metadata
    )
    detail = (
        f"page_count_in_range={page_count_in_range}, metadata_valid={metadata_valid}, "
        f"language_valid={language_valid}, tagged={tagged}, outline_valid={outline_valid}, "
        f"missing_markers={missing_markers or 'none'}, "
        f"volatile_metadata={volatile_metadata or 'none'}"
    )
    return valid, detail


def load_data() -> dict[str, pd.DataFrame]:
    scenario_summary_path = OUT_TABLES_DIR / "scenario_outcomes_summary.csv"
    scenario_plan_path = OUT_TABLES_DIR / "scenario_reallocation_plan.csv"
    scenario_stress_path = OUT_TABLES_DIR / "scenario_stress_test_summary.csv"
    seed_sensitivity_path = OUT_TABLES_DIR / "scenario_seed_sensitivity.csv"
    seed_sensitivity_summary_path = OUT_TABLES_DIR / "scenario_seed_sensitivity_summary.csv"

    return {
        "customers": pd.read_csv(RAW_DIR / "customers.csv", parse_dates=["signup_date"]),
        "transactions": pd.read_csv(RAW_DIR / "transactions.csv", parse_dates=["transaction_date"]),
        "marketing": pd.read_csv(RAW_DIR / "marketing_spend.csv", parse_dates=["date"]),
        "customer_metrics": pd.read_csv(
            PROC_DIR / "customer_metrics.csv",
            parse_dates=["first_transaction_date", "last_transaction_date"],
        ),
        "cohort_table": pd.read_csv(
            PROC_DIR / "cohort_table.csv", parse_dates=["cohort_month", "activity_month"]
        ),
        "unit_economics": pd.read_csv(PROC_DIR / "unit_economics.csv"),
        "monthly": pd.read_csv(
            OUT_TABLES_DIR / "monthly_revenue_health.csv", parse_dates=["month"]
        ),
        "revenue_decomposition": pd.read_csv(OUT_TABLES_DIR / "revenue_decomposition_effects.csv"),
        "findings": pd.read_csv(OUT_TABLES_DIR / "main_analysis_findings.csv"),
        "cohort_retention": pd.read_csv(OUT_TABLES_DIR / "cohort_retention_summary.csv"),
        "unit_econ_diagnostics": pd.read_csv(
            OUT_TABLES_DIR / "unit_economics_channel_diagnostics.csv"
        ),
        "raw_validation": pd.read_csv(OUT_TABLES_DIR / "raw_validation_summary.csv"),
        "data_quality_issues": pd.read_csv(OUT_TABLES_DIR / "data_quality_issues.csv"),
        "scenario_summary": pd.read_csv(scenario_summary_path)
        if scenario_summary_path.exists()
        else pd.DataFrame(),
        "scenario_plan": pd.read_csv(scenario_plan_path)
        if scenario_plan_path.exists()
        else pd.DataFrame(),
        "scenario_stress": pd.read_csv(scenario_stress_path)
        if scenario_stress_path.exists()
        else pd.DataFrame(),
        "seed_sensitivity": pd.read_csv(seed_sensitivity_path)
        if seed_sensitivity_path.exists()
        else pd.DataFrame(),
        "seed_sensitivity_summary": pd.read_csv(seed_sensitivity_summary_path)
        if seed_sensitivity_summary_path.exists()
        else pd.DataFrame(),
        "incrementality": pd.read_csv(OUT_TABLES_DIR / "marketing_incrementality.csv"),
        "attribution": pd.read_csv(OUT_TABLES_DIR / "multi_touch_attribution.csv"),
        "elasticity": pd.read_csv(OUT_TABLES_DIR / "pricing_elasticity.csv"),
        "pricing_recommendations": pd.read_csv(OUT_TABLES_DIR / "pricing_recommendations.csv"),
    }


def run_checks(
    data: dict[str, pd.DataFrame],
) -> tuple[list[CheckResult], list[Issue], list[str], str]:
    checks: list[CheckResult] = []
    issues: list[Issue] = []
    caveats: list[str] = []

    customers = data["customers"]
    transactions = data["transactions"]
    marketing = data["marketing"]
    customer_metrics = data["customer_metrics"]
    cohort_table = data["cohort_table"]
    monthly = data["monthly"]
    unit_economics = data["unit_economics"]
    findings = data["findings"]

    # 1) Data consistency.
    checks.append(
        CheckResult(
            "data_consistency",
            "row_count_sanity",
            "PASS"
            if len(customers) == len(customer_metrics)
            and len(transactions) > 0
            and len(marketing) > 0
            else "FAIL",
            (
                f"customers={len(customers):,}, customer_metrics={len(customer_metrics):,}, "
                f"transactions={len(transactions):,}, marketing_spend={len(marketing):,}"
            ),
        )
    )

    raw_validation = data["raw_validation"]
    raw_failures = (
        raw_validation.loc[raw_validation["status"] == "FAIL", "check_name"].astype(str).tolist()
    )
    raw_warnings = (
        raw_validation.loc[raw_validation["status"] == "WARN", "check_name"].astype(str).tolist()
    )
    checks.append(
        CheckResult(
            "data_consistency",
            "raw_validation_gate",
            "FAIL" if raw_failures else ("WARN" if raw_warnings else "PASS"),
            f"failures={raw_failures or 'none'}, warnings={raw_warnings or 'none'}",
        )
    )

    quality_issues = data["data_quality_issues"]
    blocking_quality_rows = quality_issues.loc[
        quality_issues["severity"].isin(["high", "medium"]),
        ["table_name", "check_name", "severity"],
    ]
    blocking_quality = [
        f"{row.table_name}:{row.check_name}:{row.severity}"
        for row in blocking_quality_rows.itertuples(index=False)
    ]
    checks.append(
        CheckResult(
            "data_consistency",
            "profiled_quality_issues",
            "WARN" if blocking_quality else "PASS",
            f"medium_or_high_issues={blocking_quality or 'none'}",
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

    cm_null_cols = (
        customer_metrics[["first_transaction_date", "last_transaction_date"]].isna().sum()
    )
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

    negative_margin_rows = int((transactions["cost"] > transactions["revenue"]).sum())
    negative_margin_rate = negative_margin_rows / len(transactions)
    checks.append(
        CheckResult(
            "data_consistency",
            "negative_margin_transaction_review",
            "PASS" if negative_margin_rate <= 0.01 else "WARN",
            (
                f"rows_with_cost_above_revenue={negative_margin_rows:,}, "
                f"share={negative_margin_rate:.2%}, review_threshold=1.00%"
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

    expected_unit_economics = build_unit_economics(
        customers,
        marketing,
        customer_metrics,
        transactions,
    ).sort_values("acquisition_channel", ignore_index=True)
    observed_unit_economics = unit_economics.sort_values("acquisition_channel", ignore_index=True)
    numeric_unit_columns = [
        "CAC",
        "average_LTV",
        "median_LTV",
        "total_channel_contribution_margin",
        "LTV_to_CAC",
        "payback_cac",
        "payback_aligned_spend",
        "approximate_payback_period",
        "payback_mature_customer_share",
        "payback_horizon_contribution_per_customer",
    ]
    max_unit_economics_diff = 0.0
    for column in numeric_unit_columns:
        differences = (
            pd.to_numeric(observed_unit_economics[column], errors="coerce")
            - pd.to_numeric(expected_unit_economics[column], errors="coerce")
        ).abs()
        finite_differences = differences.dropna()
        if not finite_differences.empty:
            max_unit_economics_diff = max(
                max_unit_economics_diff,
                float(finite_differences.max()),
            )
    payback_contract_columns = [
        "payback_status",
        "payback_is_censored",
        "payback_horizon_months",
        "payback_mature_customers",
    ]
    payback_contract_match = all(
        observed_unit_economics[column].tolist() == expected_unit_economics[column].tolist()
        for column in payback_contract_columns
    )
    payback_null_pattern_match = (
        observed_unit_economics["approximate_payback_period"].isna().tolist()
        == expected_unit_economics["approximate_payback_period"].isna().tolist()
    )

    checks.append(
        CheckResult(
            "calculation_checks",
            "ltv_cac_payback_logic",
            "PASS"
            if max_unit_economics_diff < 0.01
            and payback_contract_match
            and payback_null_pattern_match
            else "FAIL",
            (
                f"max_numeric_diff={max_unit_economics_diff:.6f}, "
                f"payback_contract_match={payback_contract_match}, "
                f"payback_null_pattern_match={payback_null_pattern_match}"
            ),
        )
    )

    # 3) Analytical integrity.
    joined = transactions.merge(customers[["customer_id", "segment"]], on="customer_id", how="left")
    checks.append(
        CheckResult(
            "analytical_integrity",
            "join_inflation_check",
            "PASS"
            if len(joined) == len(transactions) and int(joined["segment"].isna().sum()) == 0
            else "FAIL",
            (
                f"transactions rows pre={len(transactions):,}, post={len(joined):,}, "
                f"orphans={int(joined['segment'].isna().sum()):,}"
            ),
        )
    )

    cohort_months = cohort_table["cohort_month"].drop_duplicates().sort_values()
    final_activity_month = cohort_table["activity_month"].max()
    expected_cohort_rows = sum(
        (final_activity_month.to_period("M") - month.to_period("M")).n + 1
        for month in cohort_months
    )
    checks.append(
        CheckResult(
            "analytical_integrity",
            "cohort_month_grid_completeness",
            "PASS" if len(cohort_table) == expected_cohort_rows else "FAIL",
            f"expected_rows={expected_cohort_rows}, observed_rows={len(cohort_table)}",
        )
    )

    cohort_semantics_ok = bool(
        (cohort_table["cohort_size"] > 0).all()
        and (cohort_table["customers_active"] <= cohort_table["cohort_size"]).all()
        and (
            cohort_table["retained_month_0_customers"] <= cohort_table["month_0_active_customers"]
        ).all()
        and cohort_table[
            [
                "month_0_activation_rate",
                "signup_activity_rate",
                "retained_from_month_0_rate",
            ]
        ]
        .stack()
        .between(0.0, 1.0)
        .all()
    )
    checks.append(
        CheckResult(
            "analytical_integrity",
            "cohort_activation_and_retention_bounds",
            "PASS" if cohort_semantics_ok else "FAIL",
            (
                "cohort_size is the signup denominator; activity and retained-from-month-0 "
                f"rates remain bounded={cohort_semantics_ok}"
            ),
        )
    )

    months = int(monthly["month"].nunique())
    overlap = (
        monthly["month"].sort_values().head(6).isin(monthly["month"].sort_values().tail(6)).any()
    )
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
    residual_abs = abs(float(decomp.loc[decomp["effect"] == "residual", "effect_value"].iloc[0]))
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
            "PASS" if abs(share_sum - 1.0) <= 0.02 and residual_ratio <= 0.05 else "FAIL",
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
    eff = unit_diag.loc[
        unit_diag["efficiency_status"] == "efficient", "acquisition_channel"
    ].tolist()
    ineff = unit_diag.loc[
        unit_diag["efficiency_status"] == "inefficient", "acquisition_channel"
    ].tolist()

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
        lambda r: classify_channel_efficiency(
            r["LTV_to_CAC"],
            r["approximate_payback_period"],
            r.get("payback_status"),
        ),
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
    mandatory = expected_chart_files()
    missing = sorted(set(mandatory) - set(chart_files))

    checks.append(
        CheckResult(
            "visualization_checks",
            "mandatory_chart_coverage",
            "PASS" if len(missing) == 0 else "FAIL",
            f"charts_present={len(chart_files)}, missing={missing if missing else 'none'}",
        )
    )

    chart_readme_path = OUT_CHARTS_DIR / "README.md"
    chart_readme_text = (
        chart_readme_path.read_text(encoding="utf-8") if chart_readme_path.exists() else ""
    )
    documented_charts = set(re.findall(r"\]\(([^)]+\.png)\)", chart_readme_text))
    expected_charts = set(mandatory)
    missing_documented_charts = sorted(expected_charts - documented_charts)
    unexpected_documented_charts = sorted(documented_charts - expected_charts)
    checks.append(
        CheckResult(
            "visualization_checks",
            "chart_readme_completeness",
            "PASS"
            if not missing_documented_charts and not unexpected_documented_charts
            else "FAIL",
            (
                f"documented={len(documented_charts)}/{len(expected_charts)}, "
                f"missing={missing_documented_charts or 'none'}, "
                f"unexpected={unexpected_documented_charts or 'none'}"
            ),
        )
    )

    chart_shapes: dict[str, tuple[int, int]] = {}
    chart_errors: dict[str, str] = {}
    for path in sorted(OUT_CHARTS_DIR.glob("*.png"), key=lambda item: item.name):
        if path.name not in mandatory:
            continue
        try:
            chart_shapes[path.name] = read_png_dimensions(path)
        except (OSError, ValueError) as exc:
            chart_errors[path.name] = f"{type(exc).__name__}: {exc}"
    chart_export_ok = (
        len(chart_shapes) == len(mandatory)
        and all(height >= 600 and width >= 1_000 for height, width in chart_shapes.values())
        and not chart_errors
    )

    checks.append(
        CheckResult(
            "visualization_checks",
            "chart_file_integrity_and_dimensions",
            "PASS" if chart_export_ok else "FAIL",
            f"chart_dimensions={chart_shapes}, errors={chart_errors or 'none'}",
        )
    )

    # 5) Governance and reproducibility checks.
    metric_registry_path = REPORTS_DIR / "metric_registry.md"
    metric_registry_text = (
        metric_registry_path.read_text(encoding="utf-8") if metric_registry_path.exists() else ""
    )
    metric_registry_ok = metric_registry_path.exists() and all(
        marker in metric_registry_text
        for marker in ("# Metric Registry", "## Payback Evidence", "## Change Control")
    )
    checks.append(
        CheckResult(
            "governance_checks",
            "metric_registry_integrity",
            "PASS" if metric_registry_ok else "FAIL",
            f"metric_registry_valid={metric_registry_ok}",
        )
    )

    decision_brief_path = REPORTS_DIR / "decision_brief.md"
    decision_brief_text = (
        decision_brief_path.read_text(encoding="utf-8") if decision_brief_path.exists() else ""
    )
    decision_brief_ok = decision_brief_path.exists() and all(
        marker in decision_brief_text
        for marker in (
            "Synthetic Revenue Analytics Case",
            "## Channel Unit Economics (Observed)",
            "## Assumptions and Caveats",
        )
    )
    checks.append(
        CheckResult(
            "governance_checks",
            "decision_brief_integrity",
            "PASS" if decision_brief_ok else "FAIL",
            f"decision_brief_valid={decision_brief_ok}",
        )
    )

    data_catalog_table = OUT_TABLES_DIR / "data_catalog.csv"
    data_catalog_detail = "table_missing"
    data_catalog_ok = False
    if data_catalog_table.exists():
        try:
            catalog = pd.read_csv(data_catalog_table)
            required_catalog_columns = {
                "layer",
                "dataset",
                "column",
                "definition",
                "business_use",
            }
            data_catalog_ok = (
                required_catalog_columns.issubset(catalog.columns)
                and not catalog[["definition", "business_use"]].isna().any().any()
            )
            data_catalog_detail = (
                f"rows={len(catalog)}, datasets="
                f"{len(catalog[['layer', 'dataset']].drop_duplicates())}, "
                f"required_columns_present={required_catalog_columns.issubset(catalog.columns)}"
            )
        except (OSError, pd.errors.ParserError) as exc:
            data_catalog_detail = f"parse_error={type(exc).__name__}: {exc}"
    checks.append(
        CheckResult(
            "governance_checks",
            "data_catalog_integrity",
            "PASS" if data_catalog_ok else "FAIL",
            data_catalog_detail,
        )
    )

    analytical_report = REPORTS_DIR / "revenue_unit_economics_report.pdf"
    analytical_report_ok = (
        analytical_report.exists() and analytical_report.stat().st_size >= 100_000
    )
    checks.append(
        CheckResult(
            "governance_checks",
            "analytical_report_presence",
            "PASS" if analytical_report_ok else "FAIL",
            (
                f"report_exists={analytical_report.exists()}, "
                f"minimum_size_met={analytical_report_ok}"
            ),
        )
    )
    analytical_report_semantic_ok, analytical_report_detail = inspect_analytical_pdf(
        analytical_report
    )
    checks.append(
        CheckResult(
            "governance_checks",
            "analytical_report_integrity",
            "PASS" if analytical_report_semantic_ok else "FAIL",
            analytical_report_detail,
        )
    )

    dashboard_html_path = PROJECT_ROOT / "outputs" / "dashboard" / "growth-quality-dashboard.html"
    dashboard_text = (
        dashboard_html_path.read_text(encoding="utf-8") if dashboard_html_path.exists() else ""
    )
    dashboard_exists = dashboard_html_path.exists()
    checks.append(
        CheckResult(
            "governance_checks",
            "dashboard_presence",
            "PASS" if dashboard_exists else "FAIL",
            f"dashboard_exists={dashboard_exists}",
        )
    )
    deterministic_metadata_ok = dashboard_exists and "generated_at" not in dashboard_text
    checks.append(
        CheckResult(
            "governance_checks",
            "dashboard_deterministic_metadata",
            "PASS" if deterministic_metadata_ok else "FAIL",
            (
                "Dashboard exists and payload avoids volatile build timestamps."
                if deterministic_metadata_ok
                else "Dashboard is missing or includes volatile generated_at metadata."
            ),
        )
    )
    api_mode_contract_ok = all(
        marker in dashboard_text
        for marker in (
            "const API_MODE = false",
            "computeAndRenderFromApi",
            "/v1/dashboard/snapshot",
            "credentials: 'same-origin'",
        )
    )
    checks.append(
        CheckResult(
            "governance_checks",
            "dashboard_authenticated_api_mode_contract",
            "PASS" if api_mode_contract_ok else "FAIL",
            f"api_mode_markers_present={api_mode_contract_ok}",
        )
    )

    scenario_summary = data["scenario_summary"]
    scenario_plan = data["scenario_plan"]
    scenario_stress = data["scenario_stress"]
    seed_sensitivity = data["seed_sensitivity"]
    seed_sensitivity_summary = data["seed_sensitivity_summary"]
    scenario_ok = not scenario_summary.empty and not scenario_plan.empty
    checks.append(
        CheckResult(
            "decision_support_checks",
            "scenario_engine_outputs",
            "PASS" if scenario_ok else "FAIL",
            (
                f"scenario_summary_rows={len(scenario_summary)}, "
                f"scenario_plan_rows={len(scenario_plan)}"
            ),
        )
    )
    if scenario_ok:
        required_assumption_cols = {
            "spend_change_pct",
            "cac_elasticity",
            "ltv_elasticity",
            "scenario_cac_assumed",
            "scenario_ltv_assumed",
        }
        assumption_cols_ok = required_assumption_cols.issubset(set(scenario_plan.columns))
        checks.append(
            CheckResult(
                "decision_support_checks",
                "scenario_assumptions_auditable",
                "PASS" if assumption_cols_ok else "FAIL",
                f"required_columns_present={assumption_cols_ok}",
            )
        )
        max_scale_uplift = float(scenario_plan["spend_change_pct"].max())
        checks.append(
            CheckResult(
                "decision_support_checks",
                "scenario_scale_cap",
                "PASS" if max_scale_uplift <= MAX_SCALE_UPLIFT + 1e-6 else "FAIL",
                (
                    f"max_channel_scale_uplift={max_scale_uplift:.2%}, "
                    f"policy_cap={MAX_SCALE_UPLIFT:.2%}"
                ),
            )
        )
        scenario_spend = pd.to_numeric(scenario_plan["scenario_spend"], errors="coerce")
        scenario_spend_ok = bool(
            np.isfinite(scenario_spend).all() and (scenario_spend >= -0.01).all()
        )
        checks.append(
            CheckResult(
                "decision_support_checks",
                "scenario_spend_nonnegative_and_finite",
                "PASS" if scenario_spend_ok else "FAIL",
                (
                    f"all_scenario_spend_valid={scenario_spend_ok}, "
                    f"minimum_scenario_spend={scenario_spend.min():.2f}"
                ),
            )
        )
        baseline_budget = float(scenario_summary["total_budget_baseline"].iloc[0])
        scenario_budget = float(scenario_summary["total_budget_scenario"].iloc[0])
        unallocated_budget = float(scenario_summary["unallocated_budget"].iloc[0])
        budget_accounting_ok = (
            unallocated_budget >= -0.01
            and abs(baseline_budget - scenario_budget - unallocated_budget) <= 0.01
        )
        checks.append(
            CheckResult(
                "decision_support_checks",
                "scenario_budget_accounting",
                "PASS" if budget_accounting_ok else "FAIL",
                (
                    f"baseline_budget={baseline_budget:.2f}, scenario_budget={scenario_budget:.2f}, "
                    f"unallocated_budget={unallocated_budget:.2f}"
                ),
            )
        )
        uplift = float(scenario_summary["estimated_contribution_uplift"].iloc[0])
        scenario_baseline_contribution = float(
            scenario_summary["baseline_contribution_est"].iloc[0]
        )
        checks.append(
            CheckResult(
                "decision_support_checks",
                "scenario_baseline_reconciliation",
                "PASS" if abs(scenario_baseline_contribution - tr_margin) <= 0.01 else "FAIL",
                (
                    f"scenario_baseline_contribution={scenario_baseline_contribution:.2f}, "
                    f"observed_contribution_margin={tr_margin:.2f}"
                ),
            )
        )
        checks.append(
            CheckResult(
                "decision_support_checks",
                "scenario_uplift_is_finite",
                "PASS" if math.isfinite(uplift) else "FAIL",
                f"estimated_contribution_uplift={uplift:.2f}; sign is an output, not a QA target",
            )
        )
    stress_ok = not scenario_stress.empty
    checks.append(
        CheckResult(
            "decision_support_checks",
            "scenario_stress_test_outputs",
            "PASS" if stress_ok else "FAIL",
            f"scenario_stress_rows={len(scenario_stress)}",
        )
    )
    if stress_ok:
        by_name = scenario_stress.set_index("scenario_name")
        required_cases = {"best_case", "base_case", "worst_case"}
        has_cases = required_cases.issubset(set(by_name.index.tolist()))
        monotonic = has_cases and float(
            by_name.loc["best_case", "scenario_contribution_est"]
        ) >= float(by_name.loc["base_case", "scenario_contribution_est"]) >= float(
            by_name.loc["worst_case", "scenario_contribution_est"]
        )
        checks.append(
            CheckResult(
                "decision_support_checks",
                "scenario_stress_monotonicity",
                "PASS" if monotonic else "FAIL",
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

    sensitivity_ok = not seed_sensitivity.empty
    checks.append(
        CheckResult(
            "decision_support_checks",
            "scenario_seed_sensitivity_outputs",
            "PASS" if sensitivity_ok else "FAIL",
            f"scenario_seed_sensitivity_rows={len(seed_sensitivity)}",
        )
    )
    if sensitivity_ok:
        seeds = sorted(seed_sensitivity["seed"].astype(int).tolist())
        required_seeds = {7, 21, 42, 84, 126}
        seed_coverage_ok = required_seeds.issubset(set(seeds)) and len(seeds) == len(set(seeds))
        checks.append(
            CheckResult(
                "decision_support_checks",
                "scenario_seed_sensitivity_coverage",
                "PASS" if seed_coverage_ok else "FAIL",
                f"seeds_present={seeds}, unique={len(seeds) == len(set(seeds))}",
            )
        )

        uplift_values = pd.to_numeric(
            seed_sensitivity["estimated_contribution_uplift"], errors="coerce"
        )
        uplift_positive_rate = float((uplift_values > 0).mean())
        sensitivity_finite = bool(np.isfinite(uplift_values).all())
        checks.append(
            CheckResult(
                "decision_support_checks",
                "scenario_seed_sensitivity_values_finite",
                "PASS" if sensitivity_finite else "FAIL",
                (
                    f"all_uplifts_finite={sensitivity_finite}, "
                    f"positive_uplift_rate={uplift_positive_rate:.2%}; sign is diagnostic"
                ),
            )
        )

    checks.append(
        CheckResult(
            "decision_support_checks",
            "scenario_seed_sensitivity_summary",
            "PASS" if len(seed_sensitivity_summary) == 1 else "FAIL",
            f"scenario_seed_sensitivity_summary_rows={len(seed_sensitivity_summary)}",
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

    # Issues and caveats.
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
        checks.append(
            CheckResult(
                "governance_checks",
                "dashboard_size_budget_mb",
                "FAIL",
                "dashboard_size_mb=unavailable; dashboard output is missing",
            )
        )
        issues.append(
            Issue(
                severity="high",
                area="dashboard_outputs",
                issue="Dashboard HTML output is missing.",
                impact="Executive delivery package is incomplete.",
                recommendation="Rebuild dashboard assets and re-run validation.",
            )
        )

    incrementality = data["incrementality"]
    incrementality_numeric = incrementality.select_dtypes(include=["number"])
    incrementality_ok = bool(
        not incrementality.empty
        and np.isfinite(incrementality_numeric.to_numpy(dtype=float)).all()
        and (
            incrementality["incremental_contribution_ci_95_low"]
            <= incrementality["incremental_contribution_per_treated_customer"]
        ).all()
        and (
            incrementality["incremental_contribution_per_treated_customer"]
            <= incrementality["incremental_contribution_ci_95_high"]
        ).all()
        and incrementality["identification"].eq("randomized_customer_holdout").all()
        and incrementality["diagnostic_status"].eq("pass").all()
        and incrementality["sample_ratio_mismatch_p_value"].ge(0.01).all()
        and incrementality["pre_period_standardized_mean_difference"].abs().le(0.1).all()
    )
    checks.append(
        CheckResult(
            "causal_measurement_checks",
            "randomized_incrementality_contract",
            "PASS" if incrementality_ok else "FAIL",
            f"experiments={len(incrementality)}, finite_and_interval_valid={incrementality_ok}",
        )
    )

    attribution = data["attribution"]
    attributed_total = float(attribution["attributed_contribution"].sum())
    observed_total = float(customer_metrics["contribution_margin"].sum())
    attribution_share = float(attribution["attributed_contribution_share"].sum())
    attribution_ok = bool(
        math.isclose(attributed_total, observed_total, abs_tol=0.05)
        and math.isclose(attribution_share, 1.0, abs_tol=1e-6)
        and attribution["claim_scope"].eq("descriptive_allocation_not_incrementality").all()
    )
    checks.append(
        CheckResult(
            "causal_measurement_checks",
            "multi_touch_attribution_reconciliation",
            "PASS" if attribution_ok else "FAIL",
            (
                f"attributed_contribution={attributed_total:.2f}, "
                f"observed_contribution={observed_total:.2f}, shares={attribution_share:.6f}"
            ),
        )
    )

    elasticity = data["elasticity"]
    elasticity_numeric = elasticity.select_dtypes(include=["number"])
    elasticity_ok = bool(
        not elasticity.empty
        and np.isfinite(elasticity_numeric.to_numpy(dtype=float)).all()
        and (elasticity["price_elasticity"] < 0).all()
        and (elasticity["ci_95_low"] <= elasticity["price_elasticity"]).all()
        and (elasticity["price_elasticity"] <= elasticity["ci_95_high"]).all()
        and elasticity["price_variants"].eq(3).all()
        and elasticity["identification"].eq("randomized_weekly_price_assignment").all()
        and elasticity["standard_error_method"].eq("CR1 clustered by week_start").all()
        and elasticity["clusters"].ge(30).all()
        and elasticity["residual_dof"].gt(0).all()
        and elasticity["condition_number"].lt(1_000).all()
        and np.allclose(
            elasticity["robust_standard_error"],
            elasticity["clustered_standard_error"],
            atol=1e-8,
        )
    )
    checks.append(
        CheckResult(
            "causal_measurement_checks",
            "observed_price_elasticity_contract",
            "PASS" if elasticity_ok else "FAIL",
            f"models={len(elasticity)}, randomized_and_finite={elasticity_ok}",
        )
    )

    pricing_recommendations = data["pricing_recommendations"]
    pricing_numeric = pricing_recommendations.select_dtypes(include=["number"])
    pricing_ok = bool(
        not pricing_recommendations.empty
        and np.isfinite(pricing_numeric.to_numpy(dtype=float)).all()
        and pricing_recommendations["recommended_price_index"].between(0.90, 1.10).all()
        and (
            pricing_recommendations["recommended_price_index"]
            >= pricing_recommendations["tested_price_index_min"]
        ).all()
        and (
            pricing_recommendations["recommended_price_index"]
            <= pricing_recommendations["tested_price_index_max"]
        ).all()
    )
    checks.append(
        CheckResult(
            "causal_measurement_checks",
            "pricing_recommendation_within_tested_range",
            "PASS" if pricing_ok else "FAIL",
            f"products={len(pricing_recommendations)}, within_observed_range={pricing_ok}",
        )
    )

    warehouse_ok = False
    warehouse_detail = "warehouse_missing"
    if WAREHOUSE_PATH.exists():
        try:
            with duckdb.connect(str(WAREHOUSE_PATH), read_only=True) as connection:
                warehouse_counts = connection.execute(
                    """
                    select
                        (select count(*) from analytics_core.dim_customers),
                        (select count(*) from analytics_core.fct_transactions),
                        (select count(*) from analytics_core.fct_marketing_spend)
                    """
                ).fetchone()
                mart = connection.execute(
                    "select * from analytics_marts.mart_channel_unit_economics"
                ).fetch_df()
            expected_counts = (len(customers), len(transactions), len(marketing))
            count_ok = warehouse_counts == expected_counts
            parity = unit_economics.merge(
                mart,
                left_on="acquisition_channel",
                right_on="acquisition_channel",
                suffixes=("_python", "_warehouse"),
                validate="one_to_one",
            )
            value_ok = bool(
                np.allclose(parity["CAC"], parity["cac"], atol=1e-4)
                and np.allclose(parity["average_LTV"], parity["average_ltv"], atol=1e-4)
                and np.allclose(parity["LTV_to_CAC"], parity["ltv_to_cac"], atol=1e-4)
            )
            warehouse_ok = count_ok and value_ok and len(mart) == len(unit_economics)
            warehouse_detail = (
                f"counts={warehouse_counts}, expected={expected_counts}, "
                f"channel_rows={len(mart)}, metric_parity={value_ok}"
            )
        except Exception as exc:
            warehouse_detail = f"warehouse_error={type(exc).__name__}: {exc}"
    checks.append(
        CheckResult(
            "warehouse_checks",
            "dbt_incremental_warehouse_parity",
            "PASS" if warehouse_ok else "FAIL",
            warehouse_detail,
        )
    )

    dbt_lineage_path = GOVERNANCE_DIR / "lineage.json"
    pipeline_lineage_path = GOVERNANCE_DIR / "pipeline_lineage.json"
    operational_slas_path = GOVERNANCE_DIR / "operational_slas.json"
    governance_ok = False
    governance_detail = "governance_artifacts_missing"
    if all(
        path.exists() for path in (dbt_lineage_path, pipeline_lineage_path, operational_slas_path)
    ):
        try:
            dbt_lineage = json.loads(dbt_lineage_path.read_text(encoding="utf-8"))
            pipeline_lineage = json.loads(pipeline_lineage_path.read_text(encoding="utf-8"))
            operational_slas = json.loads(operational_slas_path.read_text(encoding="utf-8"))
            governance_ok = bool(
                dbt_lineage.get("nodes")
                and dbt_lineage.get("edges")
                and pipeline_lineage.get("nodes")
                and pipeline_lineage.get("edges")
                and operational_slas.get("data_products")
                and operational_slas.get("api", {}).get("minimum_privacy_cell_size") >= 10
            )
            governance_detail = (
                f"dbt_nodes={len(dbt_lineage.get('nodes', []))}, "
                f"pipeline_nodes={len(pipeline_lineage.get('nodes', []))}, "
                f"sla_products={len(operational_slas.get('data_products', []))}"
            )
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            governance_detail = f"governance_error={type(exc).__name__}: {exc}"
    checks.append(
        CheckResult(
            "operational_governance_checks",
            "lineage_and_sla_contracts",
            "PASS" if governance_ok else "FAIL",
            governance_detail,
        )
    )

    aggregate_api_ok = False
    aggregate_api_detail = "aggregate_api_unavailable"
    try:
        aggregate_service = AggregateDashboardService(minimum_cell_size=10)
        snapshot = aggregate_service.build_snapshot(
            DashboardFilters(
                start_date=transactions["transaction_date"].min().date(),
                end_date=transactions["transaction_date"].max().date(),
                segments=SEGMENTS,
                regions=REGIONS,
                channels=ACQUISITION_CHANNELS,
                products=PRODUCT_TYPES,
            )
        )
        serialized_snapshot = json.dumps(snapshot, allow_nan=False)
        forbidden_identifiers = ("customer_id", "transaction_id", "touchpoint_id")
        histogram_cells = snapshot.get("histogramBins", [])
        aggregate_api_ok = bool(
            aggregate_service.ready()
            and all(identifier not in serialized_snapshot for identifier in forbidden_identifiers)
            and all(
                int(cell["count"]) >= aggregate_service.minimum_cell_size
                for cell in histogram_cells
            )
        )
        aggregate_api_detail = (
            f"ready={aggregate_service.ready()}, "
            f"histogram_cells={len(histogram_cells)}, "
            f"minimum_cell_size={aggregate_service.minimum_cell_size}"
        )
    except Exception as exc:
        aggregate_api_detail = f"aggregate_api_error={type(exc).__name__}: {exc}"
    checks.append(
        CheckResult(
            "privacy_checks",
            "authenticated_aggregate_api_privacy_contract",
            "PASS" if aggregate_api_ok else "FAIL",
            aggregate_api_detail,
        )
    )

    caveats.append(
        "All findings are based on synthetic data; they demonstrate the method and must not be transferred to a real business without recalibration."
    )
    caveats.append(
        "Unit economics use observed contribution margin and period-level spend allocation; randomized lift is reported separately from descriptive multi-touch attribution."
    )
    caveats.append(
        "Payback curves use only customers old enough for the full governed horizon, align CAC to their acquisition-date window, include mature zero-transaction customers, and report unrecovered channels as right-censored."
    )
    caveats.append(
        "Revenue decomposition should be interpreted as directional decomposition, not formal causal attribution."
    )
    caveats.append(
        "Scenario engine outputs are policy simulations with illustrative, bounded CAC/LTV elasticities and a 100% channel scale-up cap; excess budget is held back when capacity is exhausted."
    )
    caveats.append(
        f"{non_tx_customers:,} customers have no observed transactions; they remain in customer-level denominators with zero contribution."
    )
    caveats.append(
        f"{negative_margin_rows:,} transactions ({negative_margin_rate:.2%}) have cost above revenue and remain in profitability calculations."
    )
    caveats.append(
        "Seed sensitivity uses repeated draws from the same synthetic data-generating process; it measures stability, not external validity."
    )
    caveats.append(
        "Experiment and pricing estimates are internally valid for their synthetic randomized assignments and observed windows; real deployment requires power analysis, interference checks, and external-validity review."
    )
    caveats.append(
        "Position-based multi-touch attribution reconciles observed contribution but does not identify incremental channel impact."
    )

    fail_count = sum(1 for c in checks if c.status == "FAIL")
    warn_count = sum(1 for c in checks if c.status == "WARN")
    has_high_issue = any(i.severity == "high" for i in issues)
    has_medium_issue = any(i.severity == "medium" for i in issues)

    if fail_count > 0 or has_high_issue:
        confidence = GATE_FAILED
    elif warn_count >= 3 or has_medium_issue:
        confidence = GATE_PASSED_WITH_CAVEATS
    else:
        confidence = GATE_PASSED

    return checks, issues, caveats, confidence


def write_outputs(
    checks: list[CheckResult],
    issues: list[Issue],
    caveats: list[str],
    confidence: str,
) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    OUT_TABLES_DIR.mkdir(parents=True, exist_ok=True)

    checks_df = pd.DataFrame([c.__dict__ for c in checks])
    issues_df = pd.DataFrame([i.__dict__ for i in issues])

    checks_df.to_csv(OUT_TABLES_DIR / "qa_checks.csv", index=False)
    issues_df.to_csv(OUT_TABLES_DIR / "qa_issues.csv", index=False)

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
        return "\n".join([header, divider, *body])

    report_lines = [
        "# QA Report",
        "",
        "Project: Revenue Analytics & Unit Economics System",
        "",
        "## Scope",
        "- Data consistency (row count, null handling, duplicate handling)",
        "- Calculation checks (revenue/cost/margin/rates/LTV/CAC/payback)",
        "- Analytical integrity (join inflation, period comparison, averaging risks, evidence alignment)",
        "- Causal measurement (randomized lift, attribution reconciliation, observed price elasticity)",
        "- Warehouse and operations (dbt parity, lineage, SLAs, privacy-safe API contract)",
        "- Visualization checks (curated chart coverage and export readability)",
        "",
        "## Summary",
        f"- PASS checks: {pass_count}",
        f"- WARN checks: {warn_count}",
        f"- FAIL checks: {fail_count}",
        f"- Analytical gate status: **{confidence}**",
        "",
        "## Checks",
        to_markdown_fallback(checks_df),
        "",
        "## Known Limitations",
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

    report_lines.extend(["", "## Caveats"])
    for caveat in caveats:
        report_lines.append(f"- {caveat}")

    report_lines.extend(
        [
            "",
            "## Output Files",
            "- `outputs/tables/qa_checks.csv`",
            "- `outputs/tables/qa_issues.csv`",
            "- `outputs/reports/qa_report.md`",
            "- `outputs/tables/scenario_reallocation_plan.csv`",
            "- `outputs/tables/scenario_outcomes_summary.csv`",
            "- `outputs/tables/scenario_stress_test_summary.csv`",
            "- `outputs/tables/scenario_seed_sensitivity.csv`",
            "- `outputs/tables/scenario_seed_sensitivity_summary.csv`",
            "- `outputs/tables/marketing_incrementality.csv`",
            "- `outputs/tables/multi_touch_attribution.csv`",
            "- `outputs/tables/pricing_elasticity.csv`",
            "- `outputs/tables/pricing_recommendations.csv`",
            "- `outputs/governance/lineage.json`",
            "- `outputs/governance/pipeline_lineage.json`",
            "- `outputs/governance/operational_slas.json`",
            "- `outputs/reports/metric_registry.md`",
            "- `outputs/tables/data_catalog.csv`",
        ]
    )

    (REPORTS_DIR / "qa_report.md").write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    data = load_data()
    checks, issues, caveats, confidence = run_checks(data)
    write_outputs(checks, issues, caveats, confidence)

    print("Final QA validation completed.")
    print(f"report: {REPORTS_DIR / 'qa_report.md'}")
    print(f"checks_csv: {OUT_TABLES_DIR / 'qa_checks.csv'}")
    print(f"issues_csv: {OUT_TABLES_DIR / 'qa_issues.csv'}")
    print(f"confidence: {confidence}")
    if confidence == GATE_FAILED:
        raise SystemExit("Final QA gate failed. Review outputs/reports/qa_report.md.")


if __name__ == "__main__":
    main()
