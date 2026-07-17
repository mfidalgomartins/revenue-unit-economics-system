"""Canonical metric and policy registry used across the analytics stack."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.paths import PROJECT_ROOT

REPORTS_DIR = PROJECT_ROOT / "outputs" / "reports"


@dataclass(frozen=True)
class EfficiencyThresholds:
    ltv_cac_target: float
    payback_target_months: float
    ineff_ltv_cac: float
    ineff_payback_months: float


@dataclass(frozen=True)
class RiskScoreWeights:
    low_efficiency_base: float
    borderline_base: float
    payback_cap_points: float
    segment_margin_floor: float
    segment_base: float
    cohort_base: float


EFFICIENCY_THRESHOLDS = EfficiencyThresholds(
    ltv_cac_target=3.0,
    payback_target_months=12.0,
    ineff_ltv_cac=1.0,
    ineff_payback_months=24.0,
)

MARGIN_QUALITY_FLOOR = 0.30
PAYBACK_HORIZON_MONTHS = 24

RISK_SCORE_WEIGHTS = RiskScoreWeights(
    low_efficiency_base=90.0,
    borderline_base=60.0,
    payback_cap_points=40.0,
    segment_margin_floor=0.35,
    segment_base=60.0,
    cohort_base=55.0,
)


def classify_channel_efficiency(
    ltv_to_cac: float,
    payback_months: float,
    payback_status: str | None = None,
) -> str:
    """Return canonical efficiency label for a channel."""
    if pd.isna(ltv_to_cac):
        return "undefined"
    if payback_status == "not_recovered":
        return "inefficient"
    if payback_status == "insufficient_maturity":
        return "undefined"
    if payback_status not in {None, "recovered"}:
        return "undefined"
    if pd.isna(payback_months):
        return "undefined"
    if (
        ltv_to_cac >= EFFICIENCY_THRESHOLDS.ltv_cac_target
        and payback_months <= EFFICIENCY_THRESHOLDS.payback_target_months
    ):
        return "efficient"
    if (
        ltv_to_cac < EFFICIENCY_THRESHOLDS.ineff_ltv_cac
        or payback_months > EFFICIENCY_THRESHOLDS.ineff_payback_months
    ):
        return "inefficient"
    return "borderline"


def channel_priority_score(
    ltv_to_cac: float,
    payback_months: float,
    payback_status: str | None = None,
) -> float:
    """Canonical risk score for channel underperformance."""
    if pd.isna(ltv_to_cac):
        return RISK_SCORE_WEIGHTS.borderline_base + 10.0

    base = (
        RISK_SCORE_WEIGHTS.low_efficiency_base
        if ltv_to_cac < EFFICIENCY_THRESHOLDS.ineff_ltv_cac
        else RISK_SCORE_WEIGHTS.borderline_base
    )
    if payback_status == "not_recovered":
        payback_component = RISK_SCORE_WEIGHTS.payback_cap_points
    elif pd.notna(payback_months):
        payback_component = min(RISK_SCORE_WEIGHTS.payback_cap_points, payback_months)
    else:
        payback_component = 15.0
    return float(base + payback_component)


def to_payload_dict() -> dict[str, object]:
    """Serialize registry values for dashboard and downstream consumers."""
    return {
        "margin_quality_floor": MARGIN_QUALITY_FLOOR,
        "payback_horizon_months": PAYBACK_HORIZON_MONTHS,
        "efficiency_thresholds": {
            "ltv_cac_target": EFFICIENCY_THRESHOLDS.ltv_cac_target,
            "payback_target_months": EFFICIENCY_THRESHOLDS.payback_target_months,
            "ineff_ltv_cac": EFFICIENCY_THRESHOLDS.ineff_ltv_cac,
            "ineff_payback_months": EFFICIENCY_THRESHOLDS.ineff_payback_months,
        },
        "risk_score_weights": {
            "low_efficiency_base": RISK_SCORE_WEIGHTS.low_efficiency_base,
            "borderline_base": RISK_SCORE_WEIGHTS.borderline_base,
            "payback_cap_points": RISK_SCORE_WEIGHTS.payback_cap_points,
            "segment_margin_floor": RISK_SCORE_WEIGHTS.segment_margin_floor,
            "segment_base": RISK_SCORE_WEIGHTS.segment_base,
            "cohort_base": RISK_SCORE_WEIGHTS.cohort_base,
        },
    }


def write_metric_registry_report() -> None:
    """Write human-readable governance report for executive and interview review."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    report = f"""# Metric Registry

This registry defines the unit-economics policy thresholds and risk-scoring defaults consumed by code and validation.

## Efficiency Classification Policy
- Efficient: `LTV/CAC >= {EFFICIENCY_THRESHOLDS.ltv_cac_target}` and `payback <= {EFFICIENCY_THRESHOLDS.payback_target_months} months`
- Inefficient: `LTV/CAC < {EFFICIENCY_THRESHOLDS.ineff_ltv_cac}`, observed payback `> {EFFICIENCY_THRESHOLDS.ineff_payback_months} months`, or CAC is not recovered within the governed horizon
- Borderline: all remaining finite cases
- Undefined: missing/invalid denominator states or insufficient cohort maturity

## Payback Evidence
- Horizon: `{PAYBACK_HORIZON_MONTHS} acquisition-age months`
- Population: customers with enough observation time to reach the full horizon, including mature customers with zero transactions
- Measure: first month where cumulative contribution per mature customer equals or exceeds channel CAC
- `not_recovered`: right-censored at the horizon and classified inefficient
- `insufficient_maturity`: no mature customer evidence and classified undefined

## Risk Scoring Defaults
- Overall margin quality floor: `{MARGIN_QUALITY_FLOOR:.0%}`
- Low-efficiency base score: `{RISK_SCORE_WEIGHTS.low_efficiency_base}`
- Borderline base score: `{RISK_SCORE_WEIGHTS.borderline_base}`
- Payback contribution cap: `{RISK_SCORE_WEIGHTS.payback_cap_points}` points
- Segment margin floor reference: `{RISK_SCORE_WEIGHTS.segment_margin_floor:.0%}`
- Segment base score: `{RISK_SCORE_WEIGHTS.segment_base}`
- Cohort base score: `{RISK_SCORE_WEIGHTS.cohort_base}`

## Causal Measurement Contracts
- Marketing incrementality: CUPED-adjusted treatment-minus-control contribution from randomized customer holdouts, reported with a 95% confidence interval
- Price elasticity: log demand response to log price using randomized weekly price assignments, fixed effects, and CR1 uncertainty clustered by week
- Valid pricing range: recommendations remain inside the observed 0.90–1.10 price index and optimize predicted contribution over bounded candidates
- Multi-touch attribution: position-based 40/20/40 allocation that reconciles observed contribution; descriptive only and never labeled incremental

## Change Control
- Thresholds and causal claim boundaries are used by analysis, dashboard classification, API publication, and validation checks.
- Any threshold change should update affected tests, recommendation guardrails, and published outputs.
"""

    (REPORTS_DIR / "metric_registry.md").write_text(report, encoding="utf-8")
