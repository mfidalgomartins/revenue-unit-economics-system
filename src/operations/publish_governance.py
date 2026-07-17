"""Publish deterministic operational SLAs and full pipeline lineage."""

from __future__ import annotations

import json
from typing import cast

from src.operations.pipeline_spec import (
    PipelineProfile,
    build_pipeline_stages,
    resolve_pipeline_profile,
    validate_stage_graph,
)
from src.paths import PROJECT_ROOT

SLA_SOURCE = PROJECT_ROOT / "config" / "operational_slas.json"
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "governance"


def load_and_validate_slas() -> dict[str, object]:
    parsed = json.loads(SLA_SOURCE.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("operational SLA catalog must be a JSON object")
    slas = cast(dict[str, object], parsed)
    products = slas.get("data_products", [])
    if not isinstance(products, list) or not products:
        raise ValueError("operational SLA catalog requires data products")
    identifiers = [product.get("id") for product in products if isinstance(product, dict)]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("operational SLA data-product IDs must be unique")
    for product in products:
        if not isinstance(product, dict) or float(product.get("max_freshness_hours", 0)) <= 0:
            raise ValueError("every data-product SLA requires positive freshness")
        path = (PROJECT_ROOT / str(product.get("path", ""))).resolve()
        if not path.is_relative_to(PROJECT_ROOT.resolve()):
            raise ValueError("SLA paths must remain inside the project root")
    return slas


def build_pipeline_lineage(
    profile: PipelineProfile | str | None = None,
) -> dict[str, object]:
    selected_profile = resolve_pipeline_profile() if profile is None else PipelineProfile(profile)
    stages = build_pipeline_stages(selected_profile)
    validate_stage_graph(stages)
    nodes = [
        {
            "id": stage.name,
            "module": stage.module,
            "sla_seconds": stage.sla_seconds,
            "timeout_seconds": stage.effective_timeout_seconds,
            "max_attempts": stage.max_attempts,
        }
        for stage in stages
    ]
    edges = [
        {"from": dependency, "to": stage.name}
        for stage in stages
        for dependency in stage.dependencies
    ]
    return {
        "schema_version": "1.0.0",
        "profile": selected_profile.value,
        "nodes": nodes,
        "edges": edges,
    }


def run() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    slas = load_and_validate_slas()
    lineage = build_pipeline_lineage()
    (OUTPUT_DIR / "operational_slas.json").write_text(
        json.dumps(slas, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (OUTPUT_DIR / "pipeline_lineage.json").write_text(
        json.dumps(lineage, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Operational governance published: {OUTPUT_DIR}")


def main() -> None:
    run()


if __name__ == "__main__":
    main()
