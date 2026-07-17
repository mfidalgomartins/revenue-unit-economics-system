"""Read-only warehouse queries and privacy-safe dashboard aggregation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd

from src.api.data_access import (
    WAREHOUSE_PATH,
    AnalyticalProductStore,
    AnalyticsWarehouse,
    CsvAnalyticalProductStore,
    DuckDbAnalyticsWarehouse,
)
from src.data_contracts import ACQUISITION_CHANNELS, PRODUCT_TYPES, REGIONS, SEGMENTS
from src.feature_engineering.build_features import build_cohort_table
from src.governance.metric_registry import (
    MARGIN_QUALITY_FLOOR,
    RISK_SCORE_WEIGHTS,
    channel_priority_score,
    classify_channel_efficiency,
    to_payload_dict,
)


class PrivacyThresholdError(ValueError):
    """Raised when a requested slice is below the governed cell size."""


@dataclass(frozen=True)
class DashboardFilters:
    start_date: date
    end_date: date
    segments: tuple[str, ...]
    regions: tuple[str, ...]
    channels: tuple[str, ...]
    products: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.start_date > self.end_date:
            raise ValueError("start_date must not be after end_date")
        domains = (
            ("segments", self.segments, SEGMENTS),
            ("regions", self.regions, REGIONS),
            ("channels", self.channels, ACQUISITION_CHANNELS),
            ("products", self.products, PRODUCT_TYPES),
        )
        for name, selected, allowed in domains:
            if not selected:
                raise ValueError(f"{name} must contain at least one value")
            unexpected = sorted(set(selected) - set(allowed))
            if unexpected:
                raise ValueError(f"{name} contains unsupported values: {unexpected}")


def _currency(value: float) -> str:
    absolute = abs(value)
    if absolute >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    if absolute >= 1_000:
        return f"${value / 1_000:.1f}K"
    return f"${value:.0f}"


def _percent(value: float) -> str:
    return f"{value:.1%}"


def _priority_band(score: float) -> str:
    if score >= 95:
        return "high"
    if score >= 70:
        return "medium"
    return "low"


class AggregateDashboardService:
    """Query warehouse facts and return only thresholded aggregate views."""

    def __init__(
        self,
        warehouse_path: Path = WAREHOUSE_PATH,
        *,
        minimum_cell_size: int = 10,
        warehouse: AnalyticsWarehouse | None = None,
        products: AnalyticalProductStore | None = None,
    ) -> None:
        if minimum_cell_size < 10:
            raise ValueError("minimum_cell_size must be at least 10")
        self.warehouse_path = warehouse_path
        self.minimum_cell_size = minimum_cell_size
        self.warehouse = warehouse or DuckDbAnalyticsWarehouse(warehouse_path)
        self.products = products or CsvAnalyticalProductStore()

    def ready(self) -> bool:
        return self.warehouse.ready() and self.products.ready()

    def bootstrap_metadata(self) -> dict[str, object]:
        coverage_start, coverage_end = self.warehouse.coverage()
        return {
            "project_name": "Revenue Analytics & Unit Economics System",
            "dashboard_title": "Growth Quality Dashboard",
            "question": "How do acquisition economics, cohort activity, and margin quality change as revenue scales?",
            "coverage_start": coverage_start.isoformat(),
            "coverage_end": coverage_end.isoformat(),
            "data_fingerprint": int(coverage_start.strftime("%Y%m%d"))
            ^ int(coverage_end.strftime("%Y%m%d")),
            "values": {
                "segments": sorted(SEGMENTS),
                "regions": sorted(REGIONS),
                "acquisition_channels": sorted(ACQUISITION_CHANNELS),
                "product_types": sorted(PRODUCT_TYPES),
            },
            "metric_policy": to_payload_dict(),
        }

    def _filtered_transactions(self, filters: DashboardFilters) -> pd.DataFrame:
        return self.warehouse.filtered_transactions(
            filters.start_date,
            filters.end_date,
            filters.segments,
            filters.regions,
            filters.channels,
            filters.products,
        )

    def _filtered_customers(self, filters: DashboardFilters) -> pd.DataFrame:
        return self.warehouse.filtered_customers(
            filters.start_date,
            filters.end_date,
            filters.segments,
            filters.regions,
            filters.channels,
        )

    def build_snapshot(self, filters: DashboardFilters) -> dict[str, Any]:
        transactions = self._filtered_transactions(filters)
        customers = self._filtered_customers(filters)
        active_customers = int(transactions["customer_id"].nunique())
        if active_customers < self.minimum_cell_size:
            raise PrivacyThresholdError(
                f"requested slice has fewer than {self.minimum_cell_size} active customers"
            )

        revenue = float(transactions["revenue"].sum())
        cost = float(transactions["cost"].sum())
        margin = revenue - cost
        margin_rate = margin / revenue if revenue else math.nan
        monthly = self._monthly(transactions)
        segments = self._profitability(transactions, "segment")
        regions = self._profitability(transactions, "region")
        average_revenue = self._average_revenue(transactions)
        histogram_bins, top_decile_share = self._histogram(transactions, customers)
        cohort, cohort_decay = self._cohort(transactions, customers)
        unit_scope_compatible = self._unit_economics_scope_compatible(filters)
        unit_economics = self._unit_economics(filters.channels) if unit_scope_compatible else []
        risks = self._risks(unit_economics, segments, cohort_decay)
        decision = self._decision(
            unit_economics,
            segments,
            regions,
            channel_economics_available=unit_scope_compatible,
        )
        insights = self._summary_insights(
            margin_rate,
            unit_economics,
            cohort,
            segments,
            top_decile_share,
            channel_economics_available=unit_scope_compatible,
        )

        kpis = [
            {
                "label": "Revenue",
                "value": _currency(revenue),
                "delta": None,
                "deltaText": "governed API slice",
                "tone": "neutral",
            },
            {
                "label": "Contribution Margin",
                "value": _currency(margin),
                "delta": None,
                "deltaText": "governed API slice",
                "tone": "good" if margin_rate >= MARGIN_QUALITY_FLOOR else "warn",
            },
            {
                "label": "Margin %",
                "value": _percent(margin_rate),
                "delta": None,
                "deltaText": "governed API slice",
                "tone": "good" if margin_rate >= MARGIN_QUALITY_FLOOR else "warn",
            },
            {
                "label": "Active Customers",
                "value": f"{active_customers:,}",
                "delta": None,
                "deltaText": "privacy-thresholded",
                "tone": "neutral",
            },
            {
                "label": "Transactions",
                "value": f"{len(transactions):,}",
                "delta": None,
                "deltaText": "privacy-thresholded",
                "tone": "neutral",
            },
            {
                "label": "Customers Acquired",
                "value": f"{customers['customer_id'].nunique():,}",
                "delta": None,
                "deltaText": "governed API slice",
                "tone": "neutral",
            },
        ]
        m6 = next((row for row in cohort if row["monthsSince"] == 6), None)
        m12 = next((row for row in cohort if row["monthsSince"] == 12), None)
        strongest_segment = max(segments, key=lambda row: float(row["margin"]), default=None)
        weakest_segment = min(segments, key=lambda row: float(row["marginPct"]), default=None)
        weakest_region = min(regions, key=lambda row: float(row["marginPct"]), default=None)
        best_channel = max(unit_economics, key=lambda row: float(row["ltvToCac"]), default=None)
        worst_channel = min(unit_economics, key=lambda row: float(row["ltvToCac"]), default=None)
        chart_insights = {
            "insight-revenue": "Monthly revenue is aggregated server-side; use the filters to compare governed slices.",
            "insight-margin": f"Selected-scope contribution margin rate is {_percent(margin_rate)}.",
            "insight-revenue-cost": f"Revenue is {_currency(revenue)} and direct cost is {_currency(cost)} for the selected scope.",
            "insight-cohort-retention": f"Median revenue retention is {_percent(float(m6['revenueRetention'])) if m6 else 'n/a'} at month 6 and {_percent(float(m12['revenueRetention'])) if m12 else 'n/a'} at month 12.",
            "insight-ltv-cac": f"{best_channel['channel']} leads and {worst_channel['channel']} trails observed LTV/CAC."
            if best_channel and worst_channel
            else "No channel comparison is available.",
            "insight-segment-margin": f"{strongest_segment['segment']} contributes the most margin; {weakest_segment['segment']} has the lowest margin rate."
            if strongest_segment and weakest_segment
            else "No segment comparison is available.",
            "insight-arpt-segment": f"{average_revenue[0]['segment']} has the highest average transaction value."
            if average_revenue
            else "No transaction-value comparison is available.",
            "insight-revenue-distribution": f"Top-decile customers contribute {_percent(top_decile_share)} of revenue; the API exposes only aggregate quantile bins.",
            "insight-region-table": f"{weakest_region['region']} has the lowest observed regional margin rate."
            if weakest_region
            else "No regional comparison is available.",
        }
        return {
            "kpis": kpis,
            "monthly": monthly,
            "cohort": cohort,
            "unitEconomics": unit_economics,
            "segments": segments,
            "averageRevenue": average_revenue,
            "histogramBins": histogram_bins,
            "regions": regions,
            "risks": risks,
            "decision": decision,
            "insights": insights,
            "chartInsights": chart_insights,
            "summaryContext": f"Current scope: {len(transactions):,} transactions | {active_customers:,} active customers",
            "privacy": {
                "minimumCellSize": self.minimum_cell_size,
                "suppressionPolicy": "rows below threshold are omitted",
            },
            "analyticalScope": {
                "selectedMetrics": "filter_aware",
                "unitEconomics": (
                    "full_coverage_channel_only"
                    if unit_scope_compatible
                    else "suppressed_incompatible_slice"
                ),
            },
        }

    def _unit_economics_scope_compatible(self, filters: DashboardFilters) -> bool:
        coverage_start, coverage_end = self.warehouse.coverage()
        return (
            filters.start_date == coverage_start
            and filters.end_date == coverage_end
            and set(filters.segments) == set(SEGMENTS)
            and set(filters.regions) == set(REGIONS)
            and set(filters.products) == set(PRODUCT_TYPES)
        )

    def _monthly(self, transactions: pd.DataFrame) -> list[dict[str, Any]]:
        work = transactions.assign(
            month=pd.to_datetime(transactions["transaction_date"]).dt.to_period("M").astype(str)
        )
        grouped = work.groupby("month", as_index=False).agg(
            revenue=("revenue", "sum"),
            cost=("cost", "sum"),
            activeCustomers=("customer_id", "nunique"),
        )
        grouped = grouped.loc[grouped["activeCustomers"] >= self.minimum_cell_size].copy()
        grouped["margin"] = grouped["revenue"] - grouped["cost"]
        return cast(list[dict[str, Any]], grouped.round(6).to_dict(orient="records"))

    def _profitability(self, transactions: pd.DataFrame, dimension: str) -> list[dict[str, Any]]:
        grouped = transactions.groupby(dimension, as_index=False).agg(
            revenue=("revenue", "sum"),
            cost=("cost", "sum"),
            customers=("customer_id", "nunique"),
        )
        grouped = grouped.loc[grouped["customers"] >= self.minimum_cell_size].copy()
        grouped["margin"] = grouped["revenue"] - grouped["cost"]
        grouped["marginPct"] = grouped["margin"] / grouped["revenue"]
        return cast(
            list[dict[str, Any]],
            grouped.sort_values("margin", ascending=False).round(6).to_dict(orient="records"),
        )

    def _average_revenue(self, transactions: pd.DataFrame) -> list[dict[str, Any]]:
        grouped = transactions.groupby("segment", as_index=False).agg(
            revenue=("revenue", "sum"),
            transactions=("transaction_id", "count"),
            customers=("customer_id", "nunique"),
        )
        grouped = grouped.loc[grouped["customers"] >= self.minimum_cell_size].copy()
        grouped["avgRevTx"] = grouped["revenue"] / grouped["transactions"]
        return cast(
            list[dict[str, Any]],
            grouped[["segment", "avgRevTx", "customers"]]
            .sort_values("avgRevTx", ascending=False)
            .round(6)
            .to_dict(orient="records"),
        )

    def _histogram(
        self,
        transactions: pd.DataFrame,
        customers: pd.DataFrame,
    ) -> tuple[list[dict[str, Any]], float]:
        del customers
        totals = transactions.groupby("customer_id", as_index=False).agg(
            total_revenue=("revenue", "sum")
        )
        totals["total_revenue"] = totals["total_revenue"].fillna(0.0)
        positive = totals.loc[totals["total_revenue"] > 0, "total_revenue"]
        if len(positive) < self.minimum_cell_size:
            return [], math.nan
        quantiles = min(10, max(1, len(positive) // self.minimum_cell_size))
        bins = pd.qcut(positive, q=quantiles, duplicates="drop")
        grouped = (
            positive.groupby(bins, observed=True)
            .agg(["min", "max", "count"])
            .reset_index(drop=True)
        )
        grouped = grouped.loc[grouped["count"] >= self.minimum_cell_size]
        rows: list[dict[str, Any]] = [
            {
                "bucketStart": float(row["min"]),
                "bucketEnd": float(row["max"]),
                "count": int(row["count"]),
            }
            for _, row in grouped.iterrows()
        ]
        sorted_values = totals["total_revenue"].sort_values(ascending=False)
        top_count = max(1, math.floor(len(sorted_values) * 0.1))
        total = float(sorted_values.sum())
        top_share = float(sorted_values.iloc[:top_count].sum()) / total if total else math.nan
        return rows, top_share

    def _cohort(
        self,
        transactions: pd.DataFrame,
        customers: pd.DataFrame,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if customers.empty or transactions.empty:
            return [], []
        customer_input = customers.copy()
        customer_input["signup_date"] = pd.to_datetime(customer_input["signup_date"])
        transaction_input = transactions[
            ["transaction_id", "customer_id", "transaction_date", "revenue", "cost", "product_type"]
        ].copy()
        transaction_input["transaction_date"] = pd.to_datetime(
            transaction_input["transaction_date"]
        )
        cohort_table = build_cohort_table(customer_input, transaction_input)
        cohort_table["monthsSince"] = (
            (cohort_table["activity_month"].dt.year - cohort_table["cohort_month"].dt.year) * 12
            + cohort_table["activity_month"].dt.month
            - cohort_table["cohort_month"].dt.month
        )
        baseline = cohort_table.loc[
            cohort_table["monthsSince"] == 0,
            ["cohort_month", "cohort_revenue", "month_0_active_customers"],
        ].rename(columns={"cohort_revenue": "baseline_revenue"})
        work = cohort_table.merge(baseline, on="cohort_month", how="left")
        work = work.loc[
            (work["month_0_active_customers_x"] >= self.minimum_cell_size)
            & (work["baseline_revenue"] > 0)
        ].copy()
        work["revenueRetention"] = work["cohort_revenue"] / work["baseline_revenue"]
        summary = (
            work.loc[work["monthsSince"] <= 24]
            .groupby("monthsSince", as_index=False)
            .agg(revenueRetention=("revenueRetention", "median"))
            .round(6)
        )
        decay = work.loc[work["monthsSince"] == 6, ["cohort_month", "revenueRetention"]].copy()
        decay["cohort"] = decay["cohort_month"].dt.strftime("%Y-%m")
        return (
            cast(list[dict[str, Any]], summary.to_dict(orient="records")),
            cast(
                list[dict[str, Any]],
                decay[["cohort", "revenueRetention"]].to_dict(orient="records"),
            ),
        )

    def _unit_economics(self, channels: tuple[str, ...]) -> list[dict[str, Any]]:
        unit = self.products.unit_economics()
        unit = unit.loc[
            unit["acquisition_channel"].isin(channels)
            & (unit["payback_mature_customers"] >= self.minimum_cell_size)
        ]
        rows: list[dict[str, Any]] = []
        for record in unit.to_dict(orient="records"):
            payback_status = str(record["payback_status"])
            payback = (
                None
                if pd.isna(record["approximate_payback_period"])
                else float(record["approximate_payback_period"])
            )
            ratio = float(record["LTV_to_CAC"])
            classification = classify_channel_efficiency(
                ratio,
                math.nan if payback is None else payback,
                payback_status,
            )
            rows.append(
                {
                    "channel": record["acquisition_channel"],
                    "customersAcquired": int(record["customers_acquired"]),
                    "totalSpend": float(record["total_spend"]),
                    "CAC": float(record["CAC"]),
                    "avgLTV": float(record["average_LTV"]),
                    "ltvToCac": ratio,
                    "paybackCAC": (
                        None if pd.isna(record["payback_cac"]) else float(record["payback_cac"])
                    ),
                    "payback": payback,
                    "paybackStatus": payback_status,
                    "paybackHorizon": int(record["payback_horizon_months"]),
                    "status": classification,
                }
            )
        return sorted(rows, key=lambda row: float(row["ltvToCac"]), reverse=True)

    def _risks(
        self,
        unit: list[dict[str, Any]],
        segments: list[dict[str, Any]],
        cohort_decay: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for record in sorted(unit, key=lambda row: float(row["ltvToCac"]))[:3]:
            ratio = float(record["ltvToCac"])
            payback = record["payback"]
            score = channel_priority_score(
                ratio,
                math.nan if payback is None else float(payback),
                str(record["paybackStatus"]),
            )
            rows.append(
                {
                    "entity": f"Channel: {record['channel']}",
                    "metricValues": f"LTV/CAC {ratio:.2f} | Payback {'>' + str(record['paybackHorizon']) if payback is None else f'{payback:.0f}'}m",
                    "riskInterpretation": "Observed LTV is below acquisition cost."
                    if ratio < 1
                    else "Channel efficiency is below the scale threshold.",
                    "recommendedAction": "Run a bounded spend holdout before changing the allocation.",
                    "priorityScore": score,
                    "priorityBand": _priority_band(score),
                }
            )
        for record in sorted(segments, key=lambda row: float(row["marginPct"]))[:2]:
            score = RISK_SCORE_WEIGHTS.segment_base + max(
                0.0,
                (RISK_SCORE_WEIGHTS.segment_margin_floor - float(record["marginPct"])) * 100,
            )
            rows.append(
                {
                    "entity": f"Segment: {record['segment']}",
                    "metricValues": f"Margin {_percent(float(record['marginPct']))} | Contribution {_currency(float(record['margin']))}",
                    "riskInterpretation": "Observed margin is below the diagnostic reference.",
                    "recommendedAction": "Decompose price, mix, and cost-to-serve before intervention.",
                    "priorityScore": score,
                    "priorityBand": _priority_band(score),
                }
            )
        for record in sorted(cohort_decay, key=lambda row: float(row["revenueRetention"]))[:2]:
            score = RISK_SCORE_WEIGHTS.cohort_base + max(
                0.0, (1 - float(record["revenueRetention"])) * 100
            )
            rows.append(
                {
                    "entity": f"Cohort: {record['cohort']}",
                    "metricValues": f"Month-6 Revenue Retention {_percent(float(record['revenueRetention']))}",
                    "riskInterpretation": "Month-6 revenue is below month 0; mechanism remains unassigned.",
                    "recommendedAction": "Split activation, retained activity, and revenue by governed dimensions.",
                    "priorityScore": score,
                    "priorityBand": _priority_band(score),
                }
            )
        return sorted(rows, key=lambda row: float(row["priorityScore"]), reverse=True)

    def _decision(
        self,
        unit: list[dict[str, Any]],
        segments: list[dict[str, Any]],
        regions: list[dict[str, Any]],
        *,
        channel_economics_available: bool = True,
    ) -> dict[str, str]:
        efficient = [str(row["channel"]) for row in unit if row["status"] == "efficient"]
        inefficient = [str(row["channel"]) for row in unit if row["status"] == "inefficient"]
        best = unit[0] if unit else None
        worst = unit[-1] if unit else None
        weakest_segment = min(segments, key=lambda row: float(row["marginPct"]), default=None)
        weakest_region = min(regions, key=lambda row: float(row["marginPct"]), default=None)
        if not channel_economics_available:
            return {
                "decision": "Channel economics unavailable for this slice",
                "decisionText": "Use full date, segment, region, and product coverage before making channel allocation decisions.",
                "scale": "Not assessed",
                "scaleText": "Full-coverage channel evidence is suppressed for this filtered scope.",
                "intervene": "Not assessed",
                "interveneText": "Absence of a channel result is not evidence of no breach.",
                "impact": f"{weakest_segment['segment']} margin {_percent(float(weakest_segment['marginPct']))}"
                if weakest_segment
                else "No segment signal",
                "impactText": f"{weakest_region['region']} has the lowest regional margin rate."
                if weakest_region
                else "No regional signal is available.",
            }
        return {
            "decision": "Pilot reductions in weak acquisition before broader scaling"
            if inefficient
            else "Scale selectively with guardrails",
            "decisionText": "Use randomized holdouts and empirical payback before committing the next allocation.",
            "scale": ", ".join(efficient) if efficient else "No channel clears all guardrails",
            "scaleText": f"{best['channel']} leads observed efficiency."
            if best
            else "No channel signal is available.",
            "intervene": ", ".join(inefficient) if inefficient else "No active breach",
            "interveneText": f"{worst['channel']} has the weakest observed LTV/CAC."
            if worst
            else "No intervention signal is available.",
            "impact": f"{weakest_segment['segment']} margin {_percent(float(weakest_segment['marginPct']))}"
            if weakest_segment
            else "No segment signal",
            "impactText": f"{weakest_region['region']} has the lowest regional margin rate."
            if weakest_region
            else "No regional signal is available.",
        }

    def _summary_insights(
        self,
        margin_rate: float,
        unit: list[dict[str, Any]],
        cohort: list[dict[str, Any]],
        segments: list[dict[str, Any]],
        top_decile_share: float,
        *,
        channel_economics_available: bool = True,
    ) -> list[dict[str, str]]:
        inefficient = [str(row["channel"]) for row in unit if row["status"] == "inefficient"]
        m6 = next((row for row in cohort if row["monthsSince"] == 6), None)
        weakest = min(segments, key=lambda row: float(row["marginPct"]), default=None)
        return [
            {
                "title": "Growth vs Margin Quality",
                "badge": "Healthy" if margin_rate >= MARGIN_QUALITY_FLOOR else "Watch",
                "tone": "good" if margin_rate >= MARGIN_QUALITY_FLOOR else "warn",
                "text": f"Selected-scope margin rate is {_percent(margin_rate)}; evaluate it with growth and mix.",
            },
            {
                "title": "Channel Efficiency Risk",
                "badge": (
                    "Unavailable"
                    if not channel_economics_available
                    else "Action"
                    if inefficient
                    else "Contained"
                ),
                "tone": (
                    "neutral"
                    if not channel_economics_available
                    else "bad"
                    if inefficient
                    else "good"
                ),
                "text": (
                    "Channel economics are unavailable for this filtered slice; no efficiency conclusion is made."
                    if not channel_economics_available
                    else f"Inefficient channels: {', '.join(inefficient)}."
                    if inefficient
                    else "No channel breaches the governed efficiency rule."
                ),
            },
            {
                "title": "Cohort Durability",
                "badge": "Stable" if m6 and float(m6["revenueRetention"]) >= 0.75 else "Decay",
                "tone": "good" if m6 and float(m6["revenueRetention"]) >= 0.75 else "bad",
                "text": f"Median month-6 revenue retention is {_percent(float(m6['revenueRetention']))}."
                if m6
                else "Month-6 retention is unavailable for this privacy-safe slice.",
            },
            {
                "title": "Profitability Concentration",
                "badge": "Concentrated",
                "tone": "warn",
                "text": f"{weakest['segment']} has the lowest segment margin; top-decile customers contribute {_percent(top_decile_share)} of revenue."
                if weakest
                else "Segment profitability is unavailable.",
            },
        ]

    def channel_metrics(self) -> list[dict[str, Any]]:
        return self._unit_economics(ACQUISITION_CHANNELS)

    def causal_metrics(self) -> dict[str, list[dict[str, Any]]]:
        incrementality = self.products.marketing_incrementality()
        incrementality = incrementality.loc[
            (incrementality["control_customers"] >= self.minimum_cell_size)
            & (incrementality["treatment_customers"] >= self.minimum_cell_size)
        ]
        elasticity = self.products.pricing_elasticity()
        elasticity = elasticity.loc[elasticity["observations"] >= self.minimum_cell_size]
        publishable_products = set(elasticity["product_scope"].astype(str)) - {"All products"}
        recommendations = self.products.pricing_recommendations()
        recommendations = recommendations.loc[
            recommendations["product_type"].isin(publishable_products)
        ]
        return {
            "incrementality": incrementality.replace({np.nan: None}).to_dict(orient="records"),
            "elasticity": elasticity.replace({np.nan: None}).to_dict(orient="records"),
            "pricingRecommendations": recommendations.replace({np.nan: None}).to_dict(
                orient="records"
            ),
        }
