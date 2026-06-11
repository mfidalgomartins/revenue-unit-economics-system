"""Measure scenario-output stability across deterministic synthetic seeds."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_TABLES_DIR = PROJECT_ROOT / "outputs" / "tables"

SENSITIVITY_SEEDS = [7, 21, 42, 84, 126]
BASELINE_SEED = 42


def _run_script(script_path: str, seed: int) -> None:
    env = os.environ.copy()
    env["SYNTHETIC_SEED"] = str(seed)
    subprocess.run(
        [sys.executable, script_path],
        cwd=PROJECT_ROOT,
        check=True,
        env=env,
    )


def _run_seed(seed: int) -> dict[str, float | int | str]:
    _run_script("src/data_generation/generate_synthetic_data.py", seed)
    _run_script("src/feature_engineering/build_features.py", seed)
    _run_script("src/scenario_engine/build_scenarios.py", seed)

    summary = pd.read_csv(OUT_TABLES_DIR / "scenario_outcomes_summary.csv").iloc[0]
    plan = pd.read_csv(OUT_TABLES_DIR / "scenario_reallocation_plan.csv")

    efficient_count = int((plan["efficiency_status"] == "efficient").sum())
    inefficient_count = int((plan["efficiency_status"] == "inefficient").sum())
    top_scale_row = plan.sort_values("spend_change", ascending=False).iloc[0]
    top_cut_row = plan.sort_values("spend_change", ascending=True).iloc[0]

    return {
        "seed": int(seed),
        "total_budget_baseline": float(summary["total_budget_baseline"]),
        "total_budget_scenario": float(summary["total_budget_scenario"]),
        "baseline_contribution_est": float(summary["baseline_contribution_est"]),
        "scenario_contribution_est": float(summary["scenario_contribution_est"]),
        "estimated_contribution_uplift": float(summary["estimated_contribution_uplift"]),
        "efficient_channels": efficient_count,
        "inefficient_channels": inefficient_count,
        "top_scale_channel": str(top_scale_row["acquisition_channel"]),
        "top_scale_spend_change": float(top_scale_row["spend_change"]),
        "top_cut_channel": str(top_cut_row["acquisition_channel"]),
        "top_cut_spend_change": float(top_cut_row["spend_change"]),
    }


def build_seed_sensitivity() -> pd.DataFrame:
    rows = [_run_seed(seed) for seed in SENSITIVITY_SEEDS]
    return pd.DataFrame(rows).sort_values("seed", ignore_index=True)


def write_outputs(sensitivity: pd.DataFrame) -> None:
    OUT_TABLES_DIR.mkdir(parents=True, exist_ok=True)

    sensitivity_out = sensitivity.copy()
    numeric_cols = [
        "total_budget_baseline",
        "total_budget_scenario",
        "baseline_contribution_est",
        "scenario_contribution_est",
        "estimated_contribution_uplift",
        "top_scale_spend_change",
        "top_cut_spend_change",
    ]
    sensitivity_out[numeric_cols] = sensitivity_out[numeric_cols].round(4)
    sensitivity_out.to_csv(OUT_TABLES_DIR / "scenario_seed_sensitivity.csv", index=False)

    uplift = sensitivity_out["estimated_contribution_uplift"]
    summary = pd.DataFrame(
        [
            {
                "seed_count": int(len(sensitivity_out)),
                "positive_uplift_rate": float((uplift > 0).mean()),
                "uplift_mean": float(uplift.mean()),
                "uplift_median": float(uplift.median()),
                "uplift_min": float(uplift.min()),
                "uplift_max": float(uplift.max()),
                "uplift_std": float(uplift.std(ddof=0)),
            }
        ]
    )
    summary.round(4).to_csv(
        OUT_TABLES_DIR / "scenario_seed_sensitivity_summary.csv",
        index=False,
    )


def restore_baseline_seed() -> None:
    _run_script("src/data_generation/generate_synthetic_data.py", BASELINE_SEED)
    _run_script("src/feature_engineering/build_features.py", BASELINE_SEED)
    _run_script("src/scenario_engine/build_scenarios.py", BASELINE_SEED)


def run() -> None:
    try:
        sensitivity = build_seed_sensitivity()
        write_outputs(sensitivity)
    finally:
        restore_baseline_seed()

    print("Scenario seed sensitivity completed.")
    print(f"sensitivity_table: {OUT_TABLES_DIR / 'scenario_seed_sensitivity.csv'}")
    print(f"summary_table: {OUT_TABLES_DIR / 'scenario_seed_sensitivity_summary.csv'}")
    print("baseline_seed_restored: 42")


def main() -> None:
    run()


if __name__ == "__main__":
    main()
