"""Run the full analytics workflow in deterministic stage order.

Each stage is run as a module (``python -m src.<stage>``) from the project root,
so ``src`` is importable without per-module ``sys.path`` manipulation.
"""

from __future__ import annotations

import os
import subprocess
import sys

from src.operations.pipeline_spec import build_pipeline_stages, resolve_pipeline_profile
from src.paths import PROJECT_ROOT


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
    profile = resolve_pipeline_profile()
    print(f"[PIPELINE] Profile: {profile.value}", flush=True)
    for stage in build_pipeline_stages(profile):
        run_step(stage.label, stage.module)
    print("[PIPELINE] Completed successfully.", flush=True)


if __name__ == "__main__":
    main()
