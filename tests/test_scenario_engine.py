from __future__ import annotations

import math

import pandas as pd
import pytest
from src.scenario_engine.build_scenarios import (
    build_reallocation_plan,
    build_stress_test_summary,
)


def test_reallocation_plan_preserves_total_budget_and_shapes_actions() -> None:
    unit_economics = pd.DataFrame(
        {
            "acquisition_channel": ["organic", "paid_search", "social_ads"],
            "customers_acquired": [100, 100, 100],
            "total_spend": [1000.0, 1000.0, 1000.0],
            "CAC": [100.0, 100.0, 100.0],
            "average_LTV": [400.0, 80.0, 50.0],
            "median_LTV": [350.0, 70.0, 45.0],
            "total_channel_contribution_margin": [40000.0, 8000.0, 5000.0],
            "LTV_to_CAC": [4.0, 0.8, 0.5],
            "approximate_payback_period": [8.0, 30.0, 35.0],
        }
    )
    marketing_spend = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01", "2024-01-01", "2024-01-01"]),
            "acquisition_channel": ["organic", "paid_search", "social_ads"],
            "spend": [1000.0, 1000.0, 1000.0],
        }
    )

    plan, summary = build_reallocation_plan(unit_economics, marketing_spend)
    s = summary.iloc[0]

    assert math.isclose(
        float(s["total_budget_baseline"]),
        float(s["total_budget_scenario"]),
        rel_tol=0,
        abs_tol=1e-6,
    )

    organic = plan.loc[plan["acquisition_channel"] == "organic"].iloc[0]
    paid = plan.loc[plan["acquisition_channel"] == "paid_search"].iloc[0]
    social = plan.loc[plan["acquisition_channel"] == "social_ads"].iloc[0]

    assert organic["scenario_spend"] > organic["baseline_spend"]
    assert organic["allocation_score"] == organic["LTV_to_CAC"]
    assert paid["scenario_spend"] < paid["baseline_spend"]
    assert social["scenario_spend"] < social["baseline_spend"]
    assert "Scale with guardrails" in organic["recommended_action"]
    assert {"spend_change_pct", "cac_elasticity", "ltv_elasticity"}.issubset(plan.columns)
    assert float(plan["spend_change_pct"].max()) <= 1.0
    assert (plan["scenario_spend"] >= 0).all()
    assert list(summary.columns) == [
        "scenario_name",
        "total_budget_baseline",
        "total_budget_scenario",
        "unallocated_budget",
        "baseline_contribution_est",
        "scenario_contribution_est",
        "estimated_contribution_uplift",
        "efficient_channels_selected",
        "inefficient_channels_selected",
    ]
    assert math.isclose(float(plan["baseline_contribution_est"].sum()), 53000.0)

    stress = build_stress_test_summary(plan)
    by_name = stress.set_index("scenario_name")
    assert (
        float(by_name.loc["best_case", "scenario_contribution_est"])
        >= float(by_name.loc["base_case", "scenario_contribution_est"])
        >= float(by_name.loc["worst_case", "scenario_contribution_est"])
    )


def test_reallocation_plan_holds_budget_when_no_efficient_channel_has_capacity() -> None:
    unit_economics = pd.DataFrame(
        {
            "acquisition_channel": ["paid_search", "social_ads"],
            "customers_acquired": [100, 100],
            "total_spend": [1000.0, 1000.0],
            "CAC": [100.0, 100.0],
            "average_LTV": [80.0, 50.0],
            "median_LTV": [70.0, 45.0],
            "total_channel_contribution_margin": [8000.0, 5000.0],
            "LTV_to_CAC": [0.8, 0.5],
            "approximate_payback_period": [30.0, 35.0],
        }
    )
    marketing_spend = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01", "2024-01-01"]),
            "acquisition_channel": ["paid_search", "social_ads"],
            "spend": [1000.0, 1000.0],
        }
    )

    _, summary = build_reallocation_plan(unit_economics, marketing_spend)
    row = summary.iloc[0]

    assert float(row["unallocated_budget"]) == 700.0
    assert float(row["total_budget_scenario"]) == 1300.0


def test_reallocation_plan_cuts_right_censored_channel() -> None:
    unit_economics = pd.DataFrame(
        {
            "acquisition_channel": ["organic", "social_ads"],
            "customers_acquired": [100, 100],
            "total_spend": [1000.0, 1000.0],
            "CAC": [100.0, 100.0],
            "average_LTV": [400.0, 400.0],
            "median_LTV": [350.0, 350.0],
            "total_channel_contribution_margin": [40000.0, 40000.0],
            "LTV_to_CAC": [4.0, 4.0],
            "approximate_payback_period": [8.0, math.nan],
            "payback_status": ["recovered", "not_recovered"],
        }
    )
    marketing_spend = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01", "2024-01-01"]),
            "acquisition_channel": ["organic", "social_ads"],
            "spend": [1000.0, 1000.0],
        }
    )

    plan, _summary = build_reallocation_plan(unit_economics, marketing_spend)
    social = plan.loc[plan["acquisition_channel"] == "social_ads"].iloc[0]

    assert social["efficiency_status"] == "inefficient"
    assert social["scenario_spend"] < social["baseline_spend"]


def test_reallocation_plan_bounds_negative_redistribution_for_asymmetric_spend() -> None:
    unit_economics = pd.DataFrame(
        {
            "acquisition_channel": ["small_high_return", "large_efficient"],
            "customers_acquired": [10, 100],
            "total_spend": [10.0, 9990.0],
            "CAC": [1.0, 99.9],
            "average_LTV": [100.0, 309.69],
            "median_LTV": [90.0, 300.0],
            "total_channel_contribution_margin": [1000.0, 30969.0],
            "LTV_to_CAC": [100.0, 3.1],
            "approximate_payback_period": [0.0, 6.0],
        }
    )
    marketing_spend = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01", "2024-01-01"]),
            "acquisition_channel": ["small_high_return", "large_efficient"],
            "spend": [10.0, 9990.0],
        }
    )

    plan, summary = build_reallocation_plan(unit_economics, marketing_spend)

    assert (plan["scenario_spend"] >= 0).all()
    assert float(plan["scenario_spend"].sum()) == pytest.approx(10_000.0)
    assert float(summary.iloc[0]["unallocated_budget"]) == pytest.approx(0.0)
