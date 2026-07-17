from __future__ import annotations

from src.governance.metric_registry import (
    EFFICIENCY_THRESHOLDS,
    MARGIN_QUALITY_FLOOR,
    channel_priority_score,
    classify_channel_efficiency,
    to_payload_dict,
)


def test_classify_channel_efficiency_thresholds() -> None:
    assert classify_channel_efficiency(3.0, 12.0) == "efficient"
    assert classify_channel_efficiency(2.5, 10.0) == "borderline"
    assert classify_channel_efficiency(0.9, 10.0) == "inefficient"
    assert classify_channel_efficiency(2.0, 30.0) == "inefficient"


def test_channel_priority_score_behaves_directionally() -> None:
    weak = channel_priority_score(0.8, 20.0)
    mid = channel_priority_score(1.5, 20.0)
    fast_payback = channel_priority_score(1.5, 5.0)

    assert weak > mid
    assert fast_payback < mid


def test_payload_dict_includes_expected_policy_keys() -> None:
    payload = to_payload_dict()
    assert "efficiency_thresholds" in payload
    assert payload["margin_quality_floor"] == MARGIN_QUALITY_FLOOR
    assert "risk_score_weights" in payload
    assert (
        payload["efficiency_thresholds"]["ltv_cac_target"] == EFFICIENCY_THRESHOLDS.ltv_cac_target
    )
