"""Measure scenario-output stability across deterministic synthetic seeds."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from src.data_generation.generate_synthetic_data import generate_datasets
from src.feature_engineering.build_features import build_customer_metrics, build_unit_economics
from src.paths import PROJECT_ROOT
from src.scenario_engine.build_scenarios import build_reallocation_plan

OUT_TABLES_DIR = PROJECT_ROOT / "outputs" / "tables"

SENSITIVITY_SEEDS = (7, 21, 42, 84, 126)


def _evaluate_seed(seed: int) -> dict[str, float | int | str]:
    """Evaluate one seed without reading or mutating canonical pipeline artifacts."""
    customers, transactions, marketing_spend = generate_datasets(seed=seed)
    customer_metrics = build_customer_metrics(customers, transactions)
    unit_economics = build_unit_economics(
        customers,
        marketing_spend,
        customer_metrics,
        transactions,
    )
    plan, summary_table = build_reallocation_plan(unit_economics, marketing_spend)
    summary = summary_table.iloc[0]

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


def build_seed_sensitivity(seeds: Iterable[int] = SENSITIVITY_SEEDS) -> pd.DataFrame:
    seed_values = tuple(int(seed) for seed in seeds)
    if not seed_values:
        raise ValueError("At least one sensitivity seed is required")
    if len(seed_values) != len(set(seed_values)):
        raise ValueError("Sensitivity seeds must be unique")

    rows = [_evaluate_seed(seed) for seed in seed_values]
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
                "seed_count": len(sensitivity_out),
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


def run() -> None:
    sensitivity = build_seed_sensitivity()
    write_outputs(sensitivity)

    print("Scenario seed sensitivity completed.")
    print(f"sensitivity_table: {OUT_TABLES_DIR / 'scenario_seed_sensitivity.csv'}")
    print(f"summary_table: {OUT_TABLES_DIR / 'scenario_seed_sensitivity_summary.csv'}")


def main() -> None:
    run()


if __name__ == "__main__":
    main()
