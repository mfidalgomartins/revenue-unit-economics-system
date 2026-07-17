"""Canonical stage graph and operational policies."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class PipelineProfile(StrEnum):
    """Supported source modes for the shared downstream analytics graph."""

    SYNTHETIC = "synthetic"
    EXTERNAL = "external"


def resolve_pipeline_profile(
    environment: Mapping[str, str] | None = None,
) -> PipelineProfile:
    """Resolve and validate the source boundary for a pipeline run."""
    values = os.environ if environment is None else environment
    raw_profile = values.get("PIPELINE_PROFILE", PipelineProfile.SYNTHETIC.value)
    try:
        profile = PipelineProfile(raw_profile)
    except ValueError as exc:
        choices = ", ".join(item.value for item in PipelineProfile)
        raise ValueError(
            f"unsupported pipeline profile {raw_profile!r}; expected one of: {choices}"
        ) from exc
    raw_data_dir = values.get("RAW_DATA_DIR", "").strip()
    if profile is PipelineProfile.SYNTHETIC and raw_data_dir:
        raise RuntimeError(
            "the synthetic pipeline profile owns data/raw; unset RAW_DATA_DIR or use external"
        )
    if profile is PipelineProfile.EXTERNAL and not raw_data_dir:
        raise RuntimeError("the external pipeline profile requires an explicit RAW_DATA_DIR")
    return profile


@dataclass(frozen=True)
class StageSpec:
    """Executable pipeline stage with dependency, retry, and SLA policy."""

    name: str
    module: str
    dependencies: tuple[str, ...]
    sla_seconds: float
    max_attempts: int = 1
    display_name: str = ""
    timeout_seconds: float | None = None

    @property
    def label(self) -> str:
        return self.display_name or self.name.replace("_", " ").title()

    @property
    def effective_timeout_seconds(self) -> float:
        return self.timeout_seconds if self.timeout_seconds is not None else self.sla_seconds * 2


def validate_stage_graph(stages: tuple[StageSpec, ...] | None = None) -> None:
    """Reject duplicate, missing, forward, or cyclic dependencies."""
    selected = PIPELINE_STAGES if stages is None else stages
    names = [stage.name for stage in selected]
    if len(names) != len(set(names)):
        raise ValueError("pipeline stage names must be unique")
    completed: set[str] = set()
    for stage in selected:
        missing = sorted(set(stage.dependencies) - set(names))
        if missing:
            raise ValueError(f"stage {stage.name!r} has unknown dependencies {missing}")
        forward = sorted(set(stage.dependencies) - completed)
        if forward:
            raise ValueError(
                f"stage {stage.name!r} depends on stages that have not completed: {forward}"
            )
        if (
            stage.sla_seconds <= 0
            or stage.max_attempts < 1
            or stage.effective_timeout_seconds < stage.sla_seconds
        ):
            raise ValueError(f"stage {stage.name!r} has invalid operational policy")
        completed.add(stage.name)


def build_pipeline_stages(
    profile: PipelineProfile | str = PipelineProfile.SYNTHETIC,
) -> tuple[StageSpec, ...]:
    """Build one validated graph with a profile-specific source boundary."""
    try:
        selected_profile = PipelineProfile(profile)
    except ValueError as exc:
        choices = ", ".join(item.value for item in PipelineProfile)
        raise ValueError(
            f"unsupported pipeline profile {profile!r}; expected one of: {choices}"
        ) from exc

    stages: list[StageSpec] = []
    raw_dependency: tuple[str, ...] = ()
    if selected_profile is PipelineProfile.SYNTHETIC:
        stages.append(
            StageSpec(
                "generate_raw",
                "src.data_generation.generate_synthetic_data",
                (),
                30,
                display_name="Generate synthetic raw data",
            )
        )
        raw_dependency = ("generate_raw",)

    stages.extend(
        (
            StageSpec(
                "validate_raw",
                "src.validation.validate_raw_data",
                raw_dependency,
                10,
                display_name="Validate raw data",
            ),
            StageSpec(
                "build_warehouse",
                "src.warehouse.run_dbt",
                ("validate_raw",),
                90,
                max_attempts=2,
                display_name="Build tested incremental warehouse models",
            ),
            StageSpec(
                "profile_raw",
                "src.data_profiling.profile_raw_data",
                ("validate_raw",),
                20,
                display_name="Profile raw data",
            ),
            StageSpec(
                "build_features",
                "src.feature_engineering.build_features",
                ("validate_raw",),
                30,
                display_name="Build engineered features",
            ),
            StageSpec(
                "analyze",
                "src.analysis.unit_economics_analysis",
                ("build_features",),
                30,
                display_name="Run core analysis",
            ),
            StageSpec(
                "measure_causal",
                "src.causal.measure_incrementality",
                ("build_features",),
                30,
                display_name="Measure incrementality and price elasticity",
            ),
            StageSpec(
                "build_scenarios",
                "src.scenario_engine.build_scenarios",
                ("analyze",),
                20,
                display_name="Build decision scenarios",
            ),
            StageSpec(
                "seed_sensitivity",
                "src.scenario_engine.build_seed_sensitivity",
                ("build_scenarios",),
                120,
                display_name="Build scenario seed sensitivity",
            ),
            StageSpec(
                "publish_operational_governance",
                "src.operations.publish_governance",
                ("build_warehouse",),
                10,
                display_name="Publish operational governance",
            ),
            StageSpec(
                "build_charts",
                "src.visualization.build_chart_pack",
                ("analyze", "measure_causal", "build_scenarios"),
                120,
                display_name="Generate curated chart pack",
            ),
            StageSpec(
                "build_dashboard",
                "src.dashboard_builder.build_dashboard_assets",
                ("analyze", "measure_causal", "build_scenarios"),
                30,
                display_name="Build executive dashboard",
            ),
            StageSpec(
                "publish_docs",
                "src.governance.publish_reports",
                ("analyze", "measure_causal", "build_scenarios"),
                20,
                display_name="Publish supporting documentation",
            ),
            StageSpec(
                "build_pdf",
                "src.governance.build_analytical_report",
                ("build_charts", "publish_docs"),
                120,
                display_name="Build analytical PDF report",
            ),
            StageSpec(
                "validate_outputs",
                "src.validation.validate_final_outputs",
                (
                    "build_warehouse",
                    "publish_operational_governance",
                    "build_dashboard",
                    "build_pdf",
                ),
                30,
                display_name="Run final QA validation",
            ),
        )
    )
    result = tuple(stages)
    validate_stage_graph(result)
    return result


PIPELINE_STAGES = build_pipeline_stages()
