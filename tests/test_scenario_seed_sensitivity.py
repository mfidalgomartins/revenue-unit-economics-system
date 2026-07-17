from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import src.scenario_engine.build_seed_sensitivity as seed_sensitivity

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_STAGE_ARTIFACTS = (
    PROJECT_ROOT / "data" / "raw" / "customers.csv",
    PROJECT_ROOT / "data" / "raw" / "transactions.csv",
    PROJECT_ROOT / "data" / "raw" / "marketing_spend.csv",
    PROJECT_ROOT / "data" / "processed" / "customer_metrics.csv",
    PROJECT_ROOT / "data" / "processed" / "cohort_table.csv",
    PROJECT_ROOT / "data" / "processed" / "unit_economics.csv",
    PROJECT_ROOT / "outputs" / "tables" / "scenario_reallocation_plan.csv",
    PROJECT_ROOT / "outputs" / "tables" / "scenario_outcomes_summary.csv",
    PROJECT_ROOT / "outputs" / "tables" / "scenario_stress_test_summary.csv",
)


def test_seed_evaluation_is_in_memory_and_matches_seed_42_baseline() -> None:
    before = {path: path.read_bytes() for path in CANONICAL_STAGE_ARTIFACTS}

    result = seed_sensitivity._evaluate_seed(42)

    assert result["seed"] == 42
    assert result["total_budget_baseline"] == pytest.approx(5_552_234.85, abs=0.01)
    assert result["total_budget_scenario"] == pytest.approx(
        result["total_budget_baseline"], abs=0.01
    )
    assert result["baseline_contribution_est"] == pytest.approx(16_564_030.67, abs=0.01)
    assert result["scenario_contribution_est"] > result["baseline_contribution_est"]
    assert result["top_cut_channel"] == "paid_search"
    assert {path: path.read_bytes() for path in CANONICAL_STAGE_ARTIFACTS} == before


@pytest.mark.parametrize("seeds", [[], [42, 42]])
def test_build_seed_sensitivity_rejects_invalid_seed_sets(seeds: list[int]) -> None:
    with pytest.raises(ValueError):
        seed_sensitivity.build_seed_sensitivity(seeds)


def test_build_seed_sensitivity_preserves_requested_evaluation_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    def fake_evaluate(seed: int) -> dict[str, int]:
        calls.append(seed)
        return {"seed": seed}

    monkeypatch.setattr(seed_sensitivity, "_evaluate_seed", fake_evaluate)
    result = seed_sensitivity.build_seed_sensitivity([42, 7])

    assert calls == [42, 7]
    assert result["seed"].tolist() == [7, 42]


def test_run_publishes_only_sensitivity_outputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sensitivity = pd.DataFrame(
        [
            {
                "seed": 42,
                "total_budget_baseline": 100.0,
                "total_budget_scenario": 100.0,
                "baseline_contribution_est": 250.0,
                "scenario_contribution_est": 275.0,
                "estimated_contribution_uplift": 25.0,
                "efficient_channels": 1,
                "inefficient_channels": 0,
                "top_scale_channel": "organic",
                "top_scale_spend_change": 10.0,
                "top_cut_channel": "paid_search",
                "top_cut_spend_change": -10.0,
            }
        ]
    )
    monkeypatch.setattr(seed_sensitivity, "OUT_TABLES_DIR", tmp_path)
    monkeypatch.setattr(
        seed_sensitivity,
        "build_seed_sensitivity",
        lambda: sensitivity,
    )

    seed_sensitivity.run()

    assert {path.name for path in tmp_path.iterdir()} == {
        "scenario_seed_sensitivity.csv",
        "scenario_seed_sensitivity_summary.csv",
    }


def test_scenario_seed_sensitivity_coverage_contract() -> None:
    sensitivity = pd.read_csv(PROJECT_ROOT / "outputs" / "tables" / "scenario_seed_sensitivity.csv")
    seeds = sorted(sensitivity["seed"].astype(int).tolist())
    assert seeds == [7, 21, 42, 84, 126]


def test_scenario_seed_sensitivity_contains_finite_uplifts() -> None:
    sensitivity = pd.read_csv(PROJECT_ROOT / "outputs" / "tables" / "scenario_seed_sensitivity.csv")
    assert sensitivity["estimated_contribution_uplift"].notna().all()


def test_scenario_seed_sensitivity_summary_contract() -> None:
    summary = pd.read_csv(
        PROJECT_ROOT / "outputs" / "tables" / "scenario_seed_sensitivity_summary.csv"
    )
    row = summary.iloc[0]

    assert int(row["seed_count"]) == 5
    assert 0.0 <= float(row["positive_uplift_rate"]) <= 1.0
