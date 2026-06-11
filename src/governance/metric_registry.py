"""Canonical metric and policy registry used across the analytics stack."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
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

RISK_SCORE_WEIGHTS = RiskScoreWeights(
    low_efficiency_base=90.0,
    borderline_base=60.0,
    payback_cap_points=40.0,
    segment_margin_floor=0.35,
    segment_base=60.0,
    cohort_base=55.0,
)


def classify_channel_efficiency(ltv_to_cac: float, payback_months: float) -> str:
    """Return canonical efficiency label for a channel."""
    if pd.isna(ltv_to_cac) or pd.isna(payback_months):
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


def channel_priority_score(ltv_to_cac: float, payback_months: float) -> float:
    """Canonical risk score for channel underperformance."""
    if pd.isna(ltv_to_cac):
        return RISK_SCORE_WEIGHTS.borderline_base + 10.0

    base = (
        RISK_SCORE_WEIGHTS.low_efficiency_base
        if ltv_to_cac < EFFICIENCY_THRESHOLDS.ineff_ltv_cac
        else RISK_SCORE_WEIGHTS.borderline_base
    )
    payback_component = (
        min(RISK_SCORE_WEIGHTS.payback_cap_points, payback_months)
        if pd.notna(payback_months)
        else 15.0
    )
    return float(base + payback_component)


def to_payload_dict() -> dict:
    """Serialize registry values for dashboard and downstream consumers."""
    return {
        "margin_quality_floor": MARGIN_QUALITY_FLOOR,
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

This registry is the single source of truth for unit-economics policy thresholds and risk-scoring defaults.

## Efficiency Classification Policy
- Efficient: `LTV/CAC >= {EFFICIENCY_THRESHOLDS.ltv_cac_target}` and `payback <= {EFFICIENCY_THRESHOLDS.payback_target_months} months`
- Inefficient: `LTV/CAC < {EFFICIENCY_THRESHOLDS.ineff_ltv_cac}` or `payback > {EFFICIENCY_THRESHOLDS.ineff_payback_months} months`
- Borderline: all remaining finite cases
- Undefined: missing or invalid denominator states

## Risk Scoring Defaults
- Overall margin quality floor: `{MARGIN_QUALITY_FLOOR:.0%}`
- Low-efficiency base score: `{RISK_SCORE_WEIGHTS.low_efficiency_base}`
- Borderline base score: `{RISK_SCORE_WEIGHTS.borderline_base}`
- Payback contribution cap: `{RISK_SCORE_WEIGHTS.payback_cap_points}` points
- Segment margin floor reference: `{RISK_SCORE_WEIGHTS.segment_margin_floor:.0%}`
- Segment base score: `{RISK_SCORE_WEIGHTS.segment_base}`
- Cohort base score: `{RISK_SCORE_WEIGHTS.cohort_base}`

## Change Control
- Thresholds are used by analysis, dashboard classification, and validation checks.
- Any threshold change should update affected tests, recommendation guardrails, and published outputs.
"""

    (REPORTS_DIR / "metric_registry.md").write_text(report, encoding="utf-8")
