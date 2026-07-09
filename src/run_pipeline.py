"""Run the full analytics workflow in deterministic stage order.

Each stage is run as a module (``python -m src.<stage>``) from the project root,
so ``src`` is importable without per-module ``sys.path`` manipulation.
"""

from __future__ import annotations

import os
import subprocess
import sys

from src.paths import PROJECT_ROOT

STEPS: list[tuple[str, str]] = [
    ("Generate synthetic raw data", "src.data_generation.generate_synthetic_data"),
    ("Validate raw data", "src.validation.validate_raw_data"),
    ("Profile raw data", "src.data_profiling.profile_raw_data"),
    ("Build engineered features", "src.feature_engineering.build_features"),
    ("Run core analysis", "src.analysis.unit_economics_analysis"),
    ("Build decision scenarios", "src.scenario_engine.build_scenarios"),
    ("Build scenario seed sensitivity", "src.scenario_engine.build_seed_sensitivity"),
    ("Generate curated chart pack", "src.visualization.build_chart_pack"),
    ("Build executive dashboard", "src.dashboard_builder.build_dashboard_assets"),
    ("Publish supporting documentation", "src.governance.publish_reports"),
    ("Build analytical PDF report", "src.governance.build_analytical_report"),
    ("Run final QA validation", "src.validation.validate_final_outputs"),
]


def run_step(step_name: str, module: str) -> None:
    command = [sys.executable, "-m", module]
    env = os.environ.copy()
    if "visualization" in module:
        env["MPLBACKEND"] = "Agg"
        mpl_cache = PROJECT_ROOT / ".cache" / "matplotlib"
        mpl_cache.mkdir(parents=True, exist_ok=True)
        env["MPLCONFIGDIR"] = str(mpl_cache)

    print(f"[PIPELINE] {step_name}...", flush=True)
    subprocess.run(command, cwd=PROJECT_ROOT, check=True, env=env)


def main() -> None:
    for step_name, module in STEPS:
        run_step(step_name, module)
    print("[PIPELINE] Completed successfully.", flush=True)


if __name__ == "__main__":
    main()
