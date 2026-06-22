from __future__ import annotations

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_scenario_seed_sensitivity_coverage_contract() -> None:
    sensitivity = pd.read_csv(
        PROJECT_ROOT / "outputs" / "tables" / "scenario_seed_sensitivity.csv"
    )
    seeds = sorted(sensitivity["seed"].astype(int).tolist())
    assert seeds == [7, 21, 42, 84, 126]


def test_scenario_seed_sensitivity_contains_finite_uplifts() -> None:
    sensitivity = pd.read_csv(
        PROJECT_ROOT / "outputs" / "tables" / "scenario_seed_sensitivity.csv"
    )
    assert sensitivity["estimated_contribution_uplift"].notna().all()


def test_scenario_seed_sensitivity_summary_contract() -> None:
    summary = pd.read_csv(
        PROJECT_ROOT / "outputs" / "tables" / "scenario_seed_sensitivity_summary.csv"
    )
    row = summary.iloc[0]

    assert int(row["seed_count"]) == 5
    assert 0.0 <= float(row["positive_uplift_rate"]) <= 1.0
