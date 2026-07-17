"""Edge-case branches in the metric registry classification and scoring."""

from __future__ import annotations

import math

from src.governance.metric_registry import (
    RISK_SCORE_WEIGHTS,
    channel_priority_score,
    classify_channel_efficiency,
)

NAN = float("nan")


def test_classify_returns_undefined_for_missing_inputs() -> None:
    assert classify_channel_efficiency(NAN, 12.0) == "undefined"
    assert classify_channel_efficiency(3.0, NAN) == "undefined"


def test_classify_uses_governed_payback_evidence_status() -> None:
    assert classify_channel_efficiency(4.0, 8.0, "recovered") == "efficient"
    assert classify_channel_efficiency(4.0, NAN, "not_recovered") == "inefficient"
    assert classify_channel_efficiency(4.0, NAN, "insufficient_maturity") == "undefined"
    assert classify_channel_efficiency(4.0, 8.0, "unexpected") == "undefined"


def test_priority_score_handles_missing_ltv() -> None:
    # Missing LTV/CAC falls back to the borderline base plus a fixed penalty.
    assert channel_priority_score(NAN, 10.0) == RISK_SCORE_WEIGHTS.borderline_base + 10.0


def test_priority_score_handles_missing_payback() -> None:
    # Valid LTV but missing payback uses the fixed payback component (15.0).
    score = channel_priority_score(1.5, NAN)
    assert math.isclose(score, RISK_SCORE_WEIGHTS.borderline_base + 15.0)


def test_priority_score_caps_payback_component() -> None:
    # Payback contribution is capped, so very long paybacks do not run away.
    capped = channel_priority_score(0.5, 999.0)
    expected = RISK_SCORE_WEIGHTS.low_efficiency_base + RISK_SCORE_WEIGHTS.payback_cap_points
    assert capped == expected
