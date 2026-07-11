"""Property-based tests for the metric registry's policy functions.

The example-based tests pin known points; these pin the *shape* of the policy
across the whole input space: classification is total and monotone in both
arguments, and the risk score is bounded and ordered the way the policy
intends. Hypothesis searches for counterexamples instead of trusting a few
hand-picked values.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st
from src.governance.metric_registry import (
    EFFICIENCY_THRESHOLDS,
    RISK_SCORE_WEIGHTS,
    channel_priority_score,
    classify_channel_efficiency,
)

QUALITY_ORDER = {"inefficient": 0, "borderline": 1, "efficient": 2}

finite_ratio = st.floats(min_value=0.0, max_value=1_000.0, allow_nan=False)
finite_payback = st.floats(min_value=0.0, max_value=1_000.0, allow_nan=False)


@given(ltv_to_cac=finite_ratio, payback=finite_payback)
def test_classification_is_total_over_finite_inputs(ltv_to_cac: float, payback: float) -> None:
    assert classify_channel_efficiency(ltv_to_cac, payback) in QUALITY_ORDER


@given(value=finite_ratio)
def test_any_nan_input_classifies_as_undefined(value: float) -> None:
    nan = float("nan")
    assert classify_channel_efficiency(nan, value) == "undefined"
    assert classify_channel_efficiency(value, nan) == "undefined"


@given(low=finite_ratio, high=finite_ratio, payback=finite_payback)
def test_more_ltv_per_cac_never_downgrades_a_channel(
    low: float, high: float, payback: float
) -> None:
    low, high = min(low, high), max(low, high)
    assert (
        QUALITY_ORDER[classify_channel_efficiency(high, payback)]
        >= QUALITY_ORDER[classify_channel_efficiency(low, payback)]
    )


@given(ltv_to_cac=finite_ratio, fast=finite_payback, slow=finite_payback)
def test_slower_payback_never_upgrades_a_channel(
    ltv_to_cac: float, fast: float, slow: float
) -> None:
    fast, slow = min(fast, slow), max(fast, slow)
    assert (
        QUALITY_ORDER[classify_channel_efficiency(ltv_to_cac, slow)]
        <= QUALITY_ORDER[classify_channel_efficiency(ltv_to_cac, fast)]
    )


@given(ltv_to_cac=finite_ratio, payback=finite_payback)
def test_priority_score_is_bounded_by_the_policy_weights(
    ltv_to_cac: float, payback: float
) -> None:
    score = channel_priority_score(ltv_to_cac, payback)
    assert RISK_SCORE_WEIGHTS.borderline_base <= score
    assert score <= RISK_SCORE_WEIGHTS.low_efficiency_base + RISK_SCORE_WEIGHTS.payback_cap_points


@given(healthy=finite_ratio, payback=finite_payback)
def test_value_destructive_channels_always_outrank_healthy_ones(
    healthy: float, payback: float
) -> None:
    destructive_ltv = EFFICIENCY_THRESHOLDS.ineff_ltv_cac / 2
    healthy_ltv = max(healthy, EFFICIENCY_THRESHOLDS.ineff_ltv_cac)
    assert channel_priority_score(destructive_ltv, payback) >= channel_priority_score(
        healthy_ltv, payback
    )
