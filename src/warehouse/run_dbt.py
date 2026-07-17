"""Run the governed dbt build and publish a deterministic lineage graph."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from src.paths import PROJECT_ROOT, RAW_DATA_DIR

DBT_PROJECT_DIR = PROJECT_ROOT / "warehouse"
LINEAGE_PATH = PROJECT_ROOT / "outputs" / "governance" / "lineage.json"


def _dbt_executable() -> Path:
    executable = Path(sys.executable).parent / "dbt"
    if not executable.exists():
        raise RuntimeError("dbt executable is unavailable; install requirements-dev.txt")
    return executable


def run_dbt_build(*, full_refresh: bool = False) -> None:
    """Build and test the selected warehouse target."""
    command = [
        str(_dbt_executable()),
        "build",
        "--project-dir",
        str(DBT_PROJECT_DIR),
        "--profiles-dir",
        str(DBT_PROJECT_DIR),
        "--no-use-colors",
    ]
    if full_refresh:
        command.append("--full-refresh")
    environment = os.environ.copy()
    environment.setdefault("RAW_DATA_DIR", str(RAW_DATA_DIR))
    environment.setdefault(
        "DBT_DUCKDB_PATH",
        str(PROJECT_ROOT / "outputs" / "duckdb" / "revenue_analytics.duckdb"),
    )
    (PROJECT_ROOT / "outputs" / "duckdb").mkdir(parents=True, exist_ok=True)
    subprocess.run(command, cwd=PROJECT_ROOT, env=environment, check=True)


def build_lineage_graph(manifest: dict[str, Any]) -> dict[str, object]:
    """Reduce dbt manifest metadata to a stable, reviewable node-edge graph."""
    resource_types = {"source", "model", "test", "exposure"}
    manifest_nodes: dict[str, dict[str, Any]] = {}
    for section in ("sources", "nodes", "exposures"):
        for unique_id, node in manifest.get(section, {}).items():
            if node.get("resource_type") in resource_types:
                manifest_nodes[unique_id] = node

    nodes = [
        {
            "id": unique_id,
            "name": node.get("name"),
            "resource_type": node.get("resource_type"),
            "package": node.get("package_name"),
            "schema": node.get("schema"),
            "owner": node.get("meta", {}).get("owner") or node.get("owner", {}).get("name"),
            "sla_hours": node.get("meta", {}).get("sla_hours"),
        }
        for unique_id, node in sorted(manifest_nodes.items())
    ]
    edges = sorted(
        {
            (dependency, unique_id)
            for unique_id, node in manifest_nodes.items()
            for dependency in node.get("depends_on", {}).get("nodes", [])
            if dependency in manifest_nodes
        }
    )
    return {
        "schema_version": "1.0.0",
        "nodes": nodes,
        "edges": [{"from": source, "to": target} for source, target in edges],
    }


def publish_lineage() -> None:
    manifest_path = DBT_PROJECT_DIR / "target" / "manifest.json"
    if not manifest_path.exists():
        raise RuntimeError("dbt manifest was not generated")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    graph = build_lineage_graph(manifest)
    LINEAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    LINEAGE_PATH.write_text(
        json.dumps(graph, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def run() -> None:
    run_dbt_build()
    publish_lineage()
    print(f"Warehouse build completed: {LINEAGE_PATH}")


def main() -> None:
    run()


if __name__ == "__main__":
    main()
