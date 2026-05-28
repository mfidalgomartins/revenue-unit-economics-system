"""Run the full analytics workflow in deterministic stage order."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

STEPS: list[tuple[str, list[str]]] = [
    ("Generate synthetic raw data", ["src/data_generation/generate_synthetic_data.py"]),
    ("Validate raw data", ["src/validation/validate_raw_data.py"]),
    ("Profile raw data", ["src/data_profiling/profile_raw_data.py"]),
    ("Build engineered features", ["src/feature_engineering/build_features.py"]),
    ("Run core analysis", ["src/analysis/unit_economics_analysis.py"]),
    ("Build decision scenarios", ["src/scenario_engine/build_scenarios.py"]),
    ("Build scenario benchmark pack", ["src/scenario_engine/build_scenario_benchmark.py"]),
    ("Generate visualization pack", ["src/visualization/generate_visuals.py"]),
    ("Generate showcase chart pack", ["src/visualization/build_chart_pack.py"]),
    ("Build executive dashboard", ["src/dashboard_builder/build_dashboard_assets.py"]),
    ("Publish governance artifacts (pre-QA)", ["src/governance/publish_governance_artifacts.py"]),
    ("Run final QA validation", ["src/validation/validate_final_outputs.py"]),
    ("Publish governance artifacts (post-QA)", ["src/governance/publish_governance_artifacts.py"]),
]


def run_step(step_name: str, script_parts: list[str]) -> None:
    command = [sys.executable, *script_parts]
    env = os.environ.copy()
    if script_parts[-1].endswith((".py",)) and "visualization/" in script_parts[-1]:
        env["MPLBACKEND"] = "Agg"
        mpl_cache = PROJECT_ROOT / ".cache" / "matplotlib"
        mpl_cache.mkdir(parents=True, exist_ok=True)
        env["MPLCONFIGDIR"] = str(mpl_cache)

    print(f"[PIPELINE] {step_name}...", flush=True)
    subprocess.run(command, cwd=PROJECT_ROOT, check=True, env=env)


def main() -> None:
    for step_name, script_parts in STEPS:
        run_step(step_name, script_parts)
    print("[PIPELINE] Completed successfully.", flush=True)


if __name__ == "__main__":
    main()
