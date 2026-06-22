"""Main analytical narrative for revenue health and unit economics.

Outputs generated:
- outputs/tables/monthly_revenue_health.csv
- outputs/tables/revenue_decomposition_effects.csv
- outputs/tables/cohort_retention_summary.csv
- outputs/tables/unit_economics_channel_diagnostics.csv
- outputs/tables/segment_profitability.csv
- outputs/tables/region_profitability.csv
- outputs/tables/product_profitability.csv
- outputs/tables/low_margin_growth_pockets.csv
- outputs/tables/main_analysis_findings.csv
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path

import numpy as np
import pandas as pd

if str(Path(__file__).resolve().parents[2]) not in sys.path:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.governance.metric_registry import (
    EFFICIENCY_THRESHOLDS,
    classify_channel_efficiency,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUT_TABLES_DIR = PROJECT_ROOT / "outputs" / "tables"


def safe_pct_change(new_value: float, base_value: float) -> float:
    if base_value == 0:
        return np.nan
    return (new_value / base_value) - 1


def fmt_currency(value: float) -> str:
    if pd.isna(value):
        return "n/a"
    return f"${value:,.0f}"


def fmt_pct(value: float) -> str:
    if pd.isna(value):
        return "n/a"
    return f"{value:.1%}"


def fmt_num(value: float, digits: int = 2) -> str:
    if pd.isna(value):
        return "n/a"
    return f"{value:,.{digits}f}"


def load_data() -> dict[str, pd.DataFrame]:
    tables = {
        "customers": pd.read_csv(RAW_DIR / "customers.csv", parse_dates=["signup_date"]),
        "transactions": pd.read_csv(
            RAW_DIR / "transactions.csv", parse_dates=["transaction_date"]
        ),
        "marketing_spend": pd.read_csv(
            RAW_DIR / "marketing_spend.csv", parse_dates=["date"]
        ),
        "customer_metrics": pd.read_csv(PROCESSED_DIR / "customer_metrics.csv"),
        "cohort_table": pd.read_csv(
            PROCESSED_DIR / "cohort_table.csv",
            parse_dates=["cohort_month", "activity_month"],
        ),
        "unit_economics": pd.read_csv(PROCESSED_DIR / "unit_economics.csv"),
    }
    return tables


def compute_overall_revenue_health(transactions: pd.DataFrame) -> tuple[pd.DataFrame, Mapping[str, object]]:
    tx = transactions.copy()
    tx["month"] = tx["transaction_date"].dt.to_period("M").dt.to_timestamp()

    monthly = (
        tx.groupby("month", as_index=False)
        .agg(
            total_revenue=("revenue", "sum"),
            total_cost=("cost", "sum"),
            transaction_count=("transaction_id", "count"),
            active_customers=("customer_id", "nunique"),
        )
        .sort_values("month", ignore_index=True)
    )
    monthly["contribution_margin"] = monthly["total_revenue"] - monthly["total_cost"]
    monthly["contribution_margin_pct"] = np.where(
        monthly["total_revenue"] > 0,
        monthly["contribution_margin"] / monthly["total_revenue"],
        np.nan,
    )

    monthly["revenue_growth_mom"] = monthly["total_revenue"].pct_change()
    monthly["cost_growth_mom"] = monthly["total_cost"].pct_change()
    monthly["contribution_margin_growth_mom"] = monthly["contribution_margin"].pct_change()

    window = 6 if len(monthly) >= 12 else max(1, len(monthly) // 2)
    early = monthly.head(window)
    recent = monthly.tail(window)

    early_rev = early["total_revenue"].mean()
    recent_rev = recent["total_revenue"].mean()
    early_cost = early["total_cost"].mean()
    recent_cost = recent["total_cost"].mean()
    early_cm = early["contribution_margin"].mean()
    recent_cm = recent["contribution_margin"].mean()

    revenue_growth = safe_pct_change(recent_rev, early_rev)
    cost_growth = safe_pct_change(recent_cost, early_cost)
    cm_growth = safe_pct_change(recent_cm, early_cm)

    monthly_periods = max(len(monthly) - 1, 1)
    revenue_cagr = safe_pct_change(
        monthly.iloc[-1]["total_revenue"], monthly.iloc[0]["total_revenue"]
    )
    if pd.notna(revenue_cagr):
        revenue_cagr = (1 + revenue_cagr) ** (1 / monthly_periods) - 1

    result = {
        "question": "Is top-line revenue scaling with improving or deteriorating contribution quality over time?",
        "metrics_used": (
            "Monthly total_revenue, total_cost, contribution_margin, contribution_margin_pct, "
            "monthly growth rates, early-vs-recent 6-month averages"
        ),
        "result": (
            f"Average monthly revenue increased from {fmt_currency(early_rev)} to {fmt_currency(recent_rev)} "
            f"({fmt_pct(revenue_growth)}), while cost increased from {fmt_currency(early_cost)} to "
            f"{fmt_currency(recent_cost)} ({fmt_pct(cost_growth)}). Contribution margin increased "
            f"{fmt_pct(cm_growth)} with latest monthly revenue CAGR around {fmt_pct(revenue_cagr)}."
        ),
        "business_interpretation": (
            "Revenue is growing in absolute terms, but sustainability depends on whether margin growth keeps pace "
            "with spend-driven volume expansion."
        ),
        "caveats": (
            "Trends are based on synthetic data and observed period windows; growth rates can be sensitive to "
            "chosen comparison window."
        ),
    }

    monthly = monthly.round(
        {
            "total_revenue": 2,
            "total_cost": 2,
            "contribution_margin": 2,
            "contribution_margin_pct": 6,
            "revenue_growth_mom": 6,
            "cost_growth_mom": 6,
            "contribution_margin_growth_mom": 6,
        }
    )
    return monthly, result


def _period_segment_stats(frame: pd.DataFrame) -> tuple[int, float, float, pd.DataFrame]:
    active_customers = int(frame["customer_id"].nunique())
    total_revenue = float(frame["revenue"].sum())
    arpc = total_revenue / active_customers if active_customers > 0 else 0.0

    seg = (
        frame.groupby("segment", as_index=False)
        .agg(
            active_customers=("customer_id", "nunique"),
            segment_revenue=("revenue", "sum"),
        )
        .sort_values("segment", ignore_index=True)
    )
    seg["share"] = np.where(active_customers > 0, seg["active_customers"] / active_customers, 0.0)
    seg["segment_arpc"] = np.where(
        seg["active_customers"] > 0,
        seg["segment_revenue"] / seg["active_customers"],
        0.0,
    )
    return active_customers, total_revenue, arpc, seg


def compute_revenue_decomposition(
    customers: pd.DataFrame,
    transactions: pd.DataFrame,
) -> tuple[pd.DataFrame, Mapping[str, object]]:
    tx = transactions.merge(customers[["customer_id", "segment"]], on="customer_id", how="left")
    tx["month"] = tx["transaction_date"].dt.to_period("M").dt.to_timestamp()
    months = sorted(tx["month"].dropna().unique())

    window = 6 if len(months) >= 12 else max(1, len(months) // 2)
    base_months = set(months[:window])
    recent_months = set(months[-window:])

    base = tx[tx["month"].isin(base_months)].copy()
    recent = tx[tx["month"].isin(recent_months)].copy()

    n0, r0, arpc0, seg0 = _period_segment_stats(base)
    n1, r1, _arpc1, seg1 = _period_segment_stats(recent)

    seg0 = seg0.set_index("segment")
    seg1 = seg1.set_index("segment")
    segments = sorted(set(seg0.index).union(set(seg1.index)))

    mix_component_per_customer = 0.0
    within_component_per_customer = 0.0
    for seg in segments:
        s0 = float(seg0.loc[seg, "share"]) if seg in seg0.index else 0.0
        a0 = float(seg0.loc[seg, "segment_arpc"]) if seg in seg0.index else 0.0
        s1 = float(seg1.loc[seg, "share"]) if seg in seg1.index else 0.0
        a1 = float(seg1.loc[seg, "segment_arpc"]) if seg in seg1.index else 0.0

        mix_component_per_customer += (s1 - s0) * a0
        within_component_per_customer += s1 * (a1 - a0)

    volume_effect = (n1 - n0) * arpc0
    mix_effect = n1 * mix_component_per_customer
    avg_revenue_effect = n1 * within_component_per_customer

    total_change = r1 - r0
    explained_total = volume_effect + mix_effect + avg_revenue_effect
    residual = total_change - explained_total

    decomposition = pd.DataFrame(
        [
            {"effect": "customer_volume_effect", "effect_value": volume_effect},
            {"effect": "mix_effect", "effect_value": mix_effect},
            {"effect": "average_revenue_effect", "effect_value": avg_revenue_effect},
            {"effect": "residual", "effect_value": residual},
            {"effect": "total_revenue_change", "effect_value": total_change},
        ]
    )

    decomposition["share_of_total_change"] = np.where(
        total_change != 0,
        decomposition["effect_value"] / total_change,
        np.nan,
    )

    dominant_row = decomposition[
        decomposition["effect"].isin(
            ["customer_volume_effect", "mix_effect", "average_revenue_effect"]
        )
    ].iloc[decomposition[
        decomposition["effect"].isin(
            ["customer_volume_effect", "mix_effect", "average_revenue_effect"]
        )
    ]["effect_value"].abs().argmax()]

    result = {
        "question": (
            "Is revenue growth primarily driven by customer volume, per-customer monetization, or "
            "customer-mix shifts?"
        ),
        "metrics_used": (
            "Revenue decomposition between first and last 6 months: customer_volume_effect, "
            "average_revenue_effect, mix_effect (segment-mix), residual"
        ),
        "result": (
            f"Revenue changed by {fmt_currency(total_change)} between comparison windows. "
            f"Volume effect: {fmt_currency(volume_effect)}, average revenue effect: {fmt_currency(avg_revenue_effect)}, "
            f"mix effect: {fmt_currency(mix_effect)}. Dominant driver: {dominant_row['effect']}."
        ),
        "business_interpretation": (
            "Growth quality is stronger when monetization and favorable mix support growth; "
            "volume-only growth with weak unit economics is less sustainable."
        ),
        "caveats": (
            "Decomposition compares aggregated windows and uses segment as the mix dimension; "
            "other mix definitions (region/product/channel) may yield different allocations."
        ),
    }

    decomposition = decomposition.round({"effect_value": 2, "share_of_total_change": 6})
    return decomposition, result


def compute_cohort_analysis(cohort_table: pd.DataFrame) -> tuple[pd.DataFrame, Mapping[str, object]]:
    cohort = cohort_table.copy()
    cohort["cohort_month"] = pd.to_datetime(cohort["cohort_month"])
    cohort["activity_month"] = pd.to_datetime(cohort["activity_month"])

    cohort["months_since_cohort"] = (
        (cohort["activity_month"].dt.year - cohort["cohort_month"].dt.year) * 12
        + (cohort["activity_month"].dt.month - cohort["cohort_month"].dt.month)
    )

    baseline = cohort[cohort["months_since_cohort"] == 0][
        ["cohort_month", "customers_active", "cohort_revenue"]
    ].rename(
        columns={
            "customers_active": "baseline_customers_active",
            "cohort_revenue": "baseline_cohort_revenue",
        }
    )

    cohort = cohort.merge(baseline, on="cohort_month", how="left")
    cohort["activity_retention"] = np.where(
        cohort["baseline_customers_active"] > 0,
        cohort["customers_active"] / cohort["baseline_customers_active"],
        np.nan,
    )
    cohort["revenue_retention"] = np.where(
        cohort["baseline_cohort_revenue"] > 0,
        cohort["cohort_revenue"] / cohort["baseline_cohort_revenue"],
        np.nan,
    )

    retention_summary = (
        cohort.groupby("months_since_cohort", as_index=False)
        .agg(
            median_activity_retention=("activity_retention", "median"),
            median_revenue_retention=("revenue_retention", "median"),
            cohorts_observed=("cohort_month", "nunique"),
        )
        .sort_values("months_since_cohort", ignore_index=True)
    )

    max_observed = cohort.groupby("cohort_month", as_index=True)["months_since_cohort"].max()

    def metric_at_month(metric_col: str, month_index: int) -> float:
        eligible = max_observed[max_observed >= month_index].index
        if len(eligible) == 0:
            return np.nan

        month_slice = cohort[
            (cohort["cohort_month"].isin(eligible))
            & (cohort["months_since_cohort"] == month_index)
        ][["cohort_month", metric_col]].set_index("cohort_month")

        series = month_slice[metric_col].reindex(eligible, fill_value=0.0)
        return float(series.median()) if len(series) else np.nan

    m3_activity = metric_at_month("activity_retention", 3)
    m6_activity = metric_at_month("activity_retention", 6)
    m12_activity = metric_at_month("activity_retention", 12)

    m3_revenue = metric_at_month("revenue_retention", 3)
    m6_revenue = metric_at_month("revenue_retention", 6)
    m12_revenue = metric_at_month("revenue_retention", 12)

    eligible_m6 = max_observed[max_observed >= 6].index
    if len(eligible_m6):
        m6_series = cohort[
            (cohort["cohort_month"].isin(eligible_m6))
            & (cohort["months_since_cohort"] == 6)
        ][["cohort_month", "revenue_retention"]].set_index("cohort_month")["revenue_retention"]
        m6_series = m6_series.reindex(eligible_m6, fill_value=0.0)
        expansion_share_m6 = float((m6_series > 1.0).mean())
    else:
        expansion_share_m6 = np.nan

    decay_signal = (
        pd.notna(m3_activity)
        and pd.notna(m6_activity)
        and m6_activity < m3_activity
    )

    result = {
        "question": (
            "Are cohorts retaining activity and revenue over time, or decaying in a way that weakens growth quality?"
        ),
        "metrics_used": (
            "Cohort activity retention and revenue retention at months 3, 6, 12; "
            "share of cohorts with month-6 revenue retention > 100%"
        ),
        "result": (
            f"Median activity retention: M3 {fmt_pct(m3_activity)}, M6 {fmt_pct(m6_activity)}, "
            f"M12 {fmt_pct(m12_activity)}. Median revenue retention: M3 {fmt_pct(m3_revenue)}, "
            f"M6 {fmt_pct(m6_revenue)}, M12 {fmt_pct(m12_revenue)}. "
            f"Cohorts with M6 revenue expansion (>100%): {fmt_pct(expansion_share_m6)}."
        ),
        "business_interpretation": (
            "Stable or expanding revenue retention suggests healthy post-acquisition monetization; "
            "declining activity retention indicates potential dependency on ongoing acquisition to sustain growth."
        ),
        "caveats": (
            "Later-month retention metrics include only mature cohorts; newer cohorts are excluded from long-horizon reads."
            + (" Cohort decay is visible between M3 and M6." if decay_signal else "")
        ),
    }

    retention_summary = retention_summary.round(
        {
            "median_activity_retention": 6,
            "median_revenue_retention": 6,
        }
    )
    return retention_summary, result


def compute_unit_economics_section(unit_economics: pd.DataFrame) -> tuple[pd.DataFrame, Mapping[str, object]]:
    ue = unit_economics.copy()

    ue["efficiency_status"] = ue.apply(
        lambda r: classify_channel_efficiency(r["LTV_to_CAC"], r["approximate_payback_period"]),
        axis=1,
    )
    ue = ue.sort_values("LTV_to_CAC", ascending=False, ignore_index=True)

    efficient_channels = ue.loc[ue["efficiency_status"] == "efficient", "acquisition_channel"].tolist()
    inefficient_channels = ue.loc[
        ue["efficiency_status"] == "inefficient", "acquisition_channel"
    ].tolist()

    best = ue.iloc[0]
    worst = ue.iloc[-1]

    result = {
        "question": "Which acquisition channels create efficient growth versus value-destructive growth?",
        "metrics_used": "CAC, average_LTV, median_LTV, LTV_to_CAC, approximate_payback_period",
        "result": (
            f"Efficient channels: {', '.join(efficient_channels) if efficient_channels else 'none'}. "
            f"Inefficient channels: {', '.join(inefficient_channels) if inefficient_channels else 'none'}. "
            f"Best LTV/CAC: {best['acquisition_channel']} ({fmt_num(best['LTV_to_CAC'], 2)}), "
            f"worst: {worst['acquisition_channel']} ({fmt_num(worst['LTV_to_CAC'], 2)})."
        ),
        "business_interpretation": (
            "Channel allocation should prioritize high LTV/CAC and faster payback channels; "
            "low-ratio channels likely drive unprofitable growth unless economics improve."
        ),
        "caveats": (
            "Unit economics use observed LTV and period-wide spend allocation; attribution and lag effects can alter "
            "real-world channel economics. Classification thresholds: "
            f"efficient when LTV/CAC >= {EFFICIENCY_THRESHOLDS.ltv_cac_target:.1f} and payback <= "
            f"{EFFICIENCY_THRESHOLDS.payback_target_months:.0f} months."
        ),
    }

    ue = ue.round(
        {
            "total_spend": 2,
            "CAC": 4,
            "average_LTV": 4,
            "median_LTV": 4,
            "LTV_to_CAC": 4,
            "approximate_payback_period": 4,
        }
    )
    return ue, result


def _profitability_table(
    frame: pd.DataFrame,
    dimension_col: str,
    revenue_col: str,
    cost_col: str,
    count_col: str,
    dimension_type: str,
    total_revenue_base: float,
) -> pd.DataFrame:
    prof = (
        frame.groupby(dimension_col, as_index=False)
        .agg(
            total_revenue=(revenue_col, "sum"),
            total_cost=(cost_col, "sum"),
            record_count=(count_col, "count"),
        )
        .rename(columns={dimension_col: "dimension_value"})
    )

    prof["contribution_margin"] = prof["total_revenue"] - prof["total_cost"]
    prof["margin_pct"] = np.where(
        prof["total_revenue"] > 0,
        prof["contribution_margin"] / prof["total_revenue"],
        np.nan,
    )
    prof["revenue_share"] = np.where(
        total_revenue_base > 0,
        prof["total_revenue"] / total_revenue_base,
        np.nan,
    )
    prof["dimension_type"] = dimension_type

    cols = [
        "dimension_type",
        "dimension_value",
        "total_revenue",
        "total_cost",
        "contribution_margin",
        "margin_pct",
        "revenue_share",
        "record_count",
    ]
    return prof[cols].sort_values("total_revenue", ascending=False, ignore_index=True)


def compute_segment_profitability(
    customers: pd.DataFrame,
    customer_metrics: pd.DataFrame,
    transactions: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, Mapping[str, object]]:
    total_revenue_base = float(transactions["revenue"].sum())

    segment_profitability = _profitability_table(
        customer_metrics,
        dimension_col="segment",
        revenue_col="total_revenue",
        cost_col="total_cost",
        count_col="customer_id",
        dimension_type="segment",
        total_revenue_base=total_revenue_base,
    )

    region_profitability = _profitability_table(
        customer_metrics,
        dimension_col="region",
        revenue_col="total_revenue",
        cost_col="total_cost",
        count_col="customer_id",
        dimension_type="region",
        total_revenue_base=total_revenue_base,
    )

    product_profitability = _profitability_table(
        transactions,
        dimension_col="product_type",
        revenue_col="revenue",
        cost_col="cost",
        count_col="transaction_id",
        dimension_type="product_type",
        total_revenue_base=total_revenue_base,
    )

    profitability_long = pd.concat(
        [segment_profitability, region_profitability, product_profitability],
        ignore_index=True,
    )

    overall_margin_pct = float(
        (transactions["revenue"].sum() - transactions["cost"].sum())
        / transactions["revenue"].sum()
    )

    low_margin_growth_pockets = profitability_long[
        (profitability_long["margin_pct"] < (overall_margin_pct - 0.10))
        & (profitability_long["revenue_share"] >= 0.05)
    ].sort_values(["margin_pct", "total_revenue"], ascending=[True, False], ignore_index=True)

    if low_margin_growth_pockets.empty:
        low_margin_growth_pockets = profitability_long[
            profitability_long["revenue_share"] >= 0.03
        ].sort_values("margin_pct", ascending=True, ignore_index=True).head(5)

    worst_segment = segment_profitability.sort_values("margin_pct", ascending=True).iloc[0]
    worst_region = region_profitability.sort_values("margin_pct", ascending=True).iloc[0]
    worst_product = product_profitability.sort_values("margin_pct", ascending=True).iloc[0]

    result = {
        "question": (
            "Which segments, regions, and products generate profitable growth, and where are low-margin "
            "growth pockets concentrated?"
        ),
        "metrics_used": (
            "Total revenue, total cost, contribution margin, margin_pct, revenue_share by segment/region/product_type"
        ),
        "result": (
            f"Lowest margin segment: {worst_segment['dimension_value']} ({fmt_pct(worst_segment['margin_pct'])}); "
            f"lowest margin region: {worst_region['dimension_value']} ({fmt_pct(worst_region['margin_pct'])}); "
            f"lowest margin product: {worst_product['dimension_value']} ({fmt_pct(worst_product['margin_pct'])}). "
            f"Low-margin growth pockets identified: {len(low_margin_growth_pockets)}."
        ),
        "business_interpretation": (
            "Growth concentration in low-margin pockets can inflate revenue while suppressing value creation. "
            "Commercial strategy should adjust pricing/mix/cost discipline in weak-margin slices."
        ),
        "caveats": (
            "Segment and region profitability use customer-level aggregated costs/revenue, while product profitability "
            "is transaction-level; direct comparisons should consider grain differences."
        ),
    }

    round_cols = [
        "total_revenue",
        "total_cost",
        "contribution_margin",
        "margin_pct",
        "revenue_share",
    ]
    for table in [
        segment_profitability,
        region_profitability,
        product_profitability,
        low_margin_growth_pockets,
    ]:
        table[round_cols] = table[round_cols].round(6)

    return (
        segment_profitability,
        region_profitability,
        product_profitability,
        low_margin_growth_pockets,
        result,
    )


def run() -> None:
    OUTPUT_TABLES_DIR.mkdir(parents=True, exist_ok=True)

    data = load_data()

    monthly_revenue_health, s1 = compute_overall_revenue_health(data["transactions"])
    revenue_decomposition, s2 = compute_revenue_decomposition(
        data["customers"], data["transactions"]
    )
    cohort_retention_summary, s3 = compute_cohort_analysis(data["cohort_table"])
    unit_econ_diagnostics, s4 = compute_unit_economics_section(data["unit_economics"])
    (
        segment_profitability,
        region_profitability,
        product_profitability,
        low_margin_growth_pockets,
        s5,
    ) = compute_segment_profitability(
        data["customers"], data["customer_metrics"], data["transactions"]
    )

    monthly_revenue_health.to_csv(OUTPUT_TABLES_DIR / "monthly_revenue_health.csv", index=False)
    revenue_decomposition.to_csv(OUTPUT_TABLES_DIR / "revenue_decomposition_effects.csv", index=False)
    cohort_retention_summary.to_csv(OUTPUT_TABLES_DIR / "cohort_retention_summary.csv", index=False)
    unit_econ_diagnostics.to_csv(
        OUTPUT_TABLES_DIR / "unit_economics_channel_diagnostics.csv", index=False
    )
    segment_profitability.to_csv(OUTPUT_TABLES_DIR / "segment_profitability.csv", index=False)
    region_profitability.to_csv(OUTPUT_TABLES_DIR / "region_profitability.csv", index=False)
    product_profitability.to_csv(OUTPUT_TABLES_DIR / "product_profitability.csv", index=False)
    low_margin_growth_pockets.to_csv(
        OUTPUT_TABLES_DIR / "low_margin_growth_pockets.csv", index=False
    )

    findings = pd.DataFrame(
        [
            {"section": "1. Overall Revenue Health", **s1},
            {"section": "2. Revenue Decomposition", **s2},
            {"section": "3. Cohort Analysis", **s3},
            {"section": "4. Unit Economics", **s4},
            {"section": "5. Segment Profitability", **s5},
        ]
    )
    findings.to_csv(OUTPUT_TABLES_DIR / "main_analysis_findings.csv", index=False)

    print("Main analysis completed.")
    print(f"findings_table: {OUTPUT_TABLES_DIR / 'main_analysis_findings.csv'}")


def main() -> None:
    run()


if __name__ == "__main__":
    main()
