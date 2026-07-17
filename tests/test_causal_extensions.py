"""Regression tests for incrementality, attribution, and elasticity outputs."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import src.causal.measure_incrementality as causal


def _experiments() -> pd.DataFrame:
    rng = np.random.default_rng(7)
    rows = []
    for index in range(200):
        treatment = index % 2 == 0
        pre = 80 + rng.normal(0, 10)
        outcome = 0.7 * pre + (18 if treatment else 0) + rng.normal(0, 8)
        rows.append(
            {
                "experiment_id": "EXP1",
                "customer_id": f"C{index}",
                "acquisition_channel": "paid_search",
                "assignment": "treatment" if treatment else "control",
                "converted": treatment or index % 5 == 0,
                "pre_period_contribution": pre,
                "observed_contribution": max(0, outcome),
            }
        )
    return pd.DataFrame(rows)


def _pricing() -> pd.DataFrame:
    rng = np.random.default_rng(9)
    rows = []
    variants = [("price_down_10", 0.9), ("control", 1.0), ("price_up_10", 1.1)]
    for week in pd.date_range("2024-01-01", periods=36, freq="W-MON"):
        for region_index, region in enumerate(("EMEA", "APAC", "LATAM")):
            for product, base, elasticity in (("Core", 100.0, -1.2), ("Premium", 200.0, -0.7)):
                assignment, multiplier = variants[(week.week + region_index) % 3]
                units = 120 * multiplier**elasticity * np.exp(rng.normal(0, 0.04))
                rows.append(
                    {
                        "week_start": week,
                        "product_type": product,
                        "region": region,
                        "assignment": assignment,
                        "observed_price": base * multiplier,
                        "units_sold": round(units),
                        "revenue": round(units) * base * multiplier,
                        "contribution_margin": round(units) * (base * multiplier - base * 0.5),
                    }
                )
    return pd.DataFrame(rows)


def test_incrementality_estimate_detects_randomized_lift() -> None:
    result = causal.build_incrementality_estimates(_experiments())

    assert len(result) == 1
    row = result.iloc[0]
    assert row["identification"] == "randomized_customer_holdout"
    assert row["incremental_contribution_per_treated_customer"] > 10
    assert row["incremental_contribution_ci_95_low"] > 0
    assert row["treatment_customers"] == row["control_customers"]
    assert 0 <= row["p_value"] <= 1
    assert row["sample_ratio_mismatch_p_value"] >= 0.01
    assert abs(row["pre_period_standardized_mean_difference"]) <= 0.1
    assert row["diagnostic_status"] == "pass"


def test_incrementality_rejects_bad_contracts_and_arms() -> None:
    with pytest.raises(ValueError, match="missing columns"):
        causal.build_incrementality_estimates(pd.DataFrame({"experiment_id": ["x"]}))
    one_arm = _experiments().query("assignment == 'control'")
    with pytest.raises(ValueError, match="both randomized arms"):
        causal.build_incrementality_estimates(one_arm)
    tiny = _experiments().iloc[:2].copy()
    tiny["assignment"] = ["control", "treatment"]
    with pytest.raises(ValueError, match="at least two observations"):
        causal.build_incrementality_estimates(tiny)


def test_position_attribution_reconciles_customer_and_contribution_totals() -> None:
    touchpoints = pd.DataFrame(
        {
            "touchpoint_id": ["T1", "T2", "T3", "T4", "T5", "T6"],
            "customer_id": ["C1", "C2", "C2", "C3", "C3", "C3"],
            "acquisition_channel": [
                "organic",
                "email",
                "paid_search",
                "social_ads",
                "email",
                "organic",
            ],
            "touchpoint_order": [1, 1, 2, 1, 2, 3],
        }
    )
    customers = pd.DataFrame(
        {"customer_id": ["C1", "C2", "C3"], "contribution_margin": [100.0, 200.0, 300.0]}
    )

    result = causal.build_multi_touch_attribution(touchpoints, customers)

    assert result["attributed_customer_equivalents"].sum() == pytest.approx(3.0)
    assert result["attributed_contribution"].sum() == pytest.approx(600.0)
    assert result["attributed_contribution_share"].sum() == pytest.approx(1.0)
    assert set(result["claim_scope"]) == {"descriptive_allocation_not_incrementality"}
    assert causal._position_weights(1).tolist() == [1.0]
    assert causal._position_weights(2).tolist() == [0.5, 0.5]
    with pytest.raises(ValueError, match="positive"):
        causal._position_weights(0)


def test_attribution_rejects_missing_columns_and_unknown_customers() -> None:
    with pytest.raises(ValueError, match="touchpoints missing"):
        causal.build_multi_touch_attribution(pd.DataFrame(), pd.DataFrame())
    touchpoints = pd.DataFrame(
        {
            "touchpoint_id": ["T1"],
            "customer_id": ["missing"],
            "acquisition_channel": ["organic"],
            "touchpoint_order": [1],
        }
    )
    with pytest.raises(ValueError, match="absent"):
        causal.build_multi_touch_attribution(
            touchpoints,
            pd.DataFrame({"customer_id": ["C1"], "contribution_margin": [1.0]}),
        )


def test_elasticity_and_bounded_pricing_recommendations() -> None:
    pricing = _pricing()
    elasticity = causal.estimate_price_elasticity(pricing)
    recommendations = causal.build_elasticity_pricing_recommendations(pricing, elasticity)

    assert set(elasticity["product_scope"]) == {"All products", "Core", "Premium"}
    assert elasticity["price_elasticity"].between(-2.0, -0.2).all()
    assert (elasticity["ci_95_low"] < elasticity["ci_95_high"]).all()
    assert elasticity["standard_error_method"].eq("CR1 clustered by week_start").all()
    assert elasticity["clusters"].eq(36).all()
    assert elasticity["clustered_standard_error"].gt(0).all()
    assert elasticity["condition_number"].lt(1_000).all()
    assert recommendations["recommended_price_index"].between(0.95, 1.05).all()
    assert recommendations["predicted_weekly_contribution"].gt(0).all()


def test_elasticity_rejects_weak_identification() -> None:
    with pytest.raises(ValueError, match="missing columns"):
        causal.estimate_price_elasticity(pd.DataFrame())
    pricing = _pricing().query("assignment == 'control'")
    with pytest.raises(ValueError, match="all three"):
        causal.estimate_price_elasticity(pricing)
    sparse = _pricing().iloc[:20]
    with pytest.raises(ValueError, match="at least 30"):
        causal._fit_log_demand_model(sparse, product_scope="Core")


def test_causal_run_writes_all_governed_outputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(causal, "TABLES_DIR", tmp_path)
    causal.run()
    assert {path.name for path in tmp_path.glob("*.csv")} == {
        "marketing_incrementality.csv",
        "multi_touch_attribution.csv",
        "pricing_elasticity.csv",
        "pricing_recommendations.csv",
    }
