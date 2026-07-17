"""Integration coverage for the stage orchestration entry points.

Each stage's ``run()`` reads the committed deterministic inputs and writes its
outputs to a single module-level directory. The tests redirect only that output
directory to a temporary path, so the orchestration and writer code is exercised
end to end without mutating any tracked artifact.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import src.analysis.unit_economics_analysis as analysis
import src.dashboard_builder.build_dashboard_assets as dashboard
import src.data_profiling.profile_raw_data as profiling
import src.feature_engineering.build_features as features
import src.governance.data_catalog as data_catalog
import src.governance.metric_registry as metric_registry
import src.governance.publish_reports as publish_reports
import src.run_pipeline as pipeline
import src.scenario_engine.build_scenarios as scenarios
import src.validation.validate_raw_data as validate_raw
from src.operations.pipeline_spec import PipelineProfile, StageSpec
from src.paths import PROJECT_ROOT, resolve_raw_data_dir


def test_build_features_run_writes_processed_tables(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(features, "PROCESSED_DIR", tmp_path)
    features.run()
    for name in ("customer_metrics.csv", "cohort_table.csv", "unit_economics.csv"):
        assert (tmp_path / name).exists()


def test_dashboard_run_writes_selfcontained_html(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(dashboard, "DASHBOARD_DIR", tmp_path)
    dashboard.run()
    html = (tmp_path / "growth-quality-dashboard.html").read_text(encoding="utf-8")
    assert "__DATA_JSON__" not in html
    assert "decodePayload" in html
    assert html.startswith("<!DOCTYPE html>")


def test_analysis_run_writes_all_section_tables(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(analysis, "OUTPUT_TABLES_DIR", tmp_path)
    analysis.run()
    for name in (
        "monthly_revenue_health.csv",
        "revenue_decomposition_effects.csv",
        "cohort_retention_summary.csv",
        "unit_economics_channel_diagnostics.csv",
        "segment_profitability.csv",
        "region_profitability.csv",
        "product_profitability.csv",
        "main_analysis_findings.csv",
    ):
        assert (tmp_path / name).exists()


def test_validate_raw_run_writes_summary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(validate_raw, "OUT_TABLES_DIR", tmp_path)
    validate_raw.run()
    assert (tmp_path / "raw_validation_summary.csv").exists()


def test_profiling_run_writes_quality_outputs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(profiling, "OUTPUT_TABLES_DIR", tmp_path)
    profiling.run()
    assert (tmp_path / "data_profile_summary.csv").exists()
    assert (tmp_path / "data_quality_issues.csv").exists()


def test_scenarios_run_writes_plan_and_summaries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(scenarios, "OUT_TABLES_DIR", tmp_path)
    scenarios.run()
    for name in (
        "scenario_reallocation_plan.csv",
        "scenario_outcomes_summary.csv",
        "scenario_stress_test_summary.csv",
    ):
        assert (tmp_path / name).exists()


def test_metric_registry_writer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(metric_registry, "REPORTS_DIR", tmp_path)
    metric_registry.write_metric_registry_report()
    report = (tmp_path / "metric_registry.md").read_text(encoding="utf-8")
    assert "Metric Registry" in report
    assert "Efficiency Classification Policy" in report


def test_data_catalog_writer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(data_catalog, "OUT_TABLES_DIR", tmp_path)
    data_catalog.write_data_catalog_artifacts()
    assert (tmp_path / "data_catalog.csv").exists()


def test_decision_brief_writer_handles_censored_payback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(publish_reports, "REPORTS_DIR", tmp_path)

    publish_reports.write_decision_brief()

    brief = (tmp_path / "decision_brief.md").read_text(encoding="utf-8")
    assert "Synthetic Revenue Analytics Case" in brief
    assert ">24m (not recovered)" in brief
    assert "nanm" not in brief


def test_pipeline_run_step_uses_current_interpreter_and_project_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[list[str], Path, bool, dict[str, str]]] = []

    def capture_run(
        command: list[str],
        *,
        cwd: Path,
        check: bool,
        env: dict[str, str],
    ) -> None:
        calls.append((command, cwd, check, env))

    monkeypatch.setattr(pipeline, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(pipeline.subprocess, "run", capture_run)

    pipeline.run_step("Charts", "src.visualization.build_chart_pack")

    command, cwd, check, env = calls[0]
    assert command == [pipeline.sys.executable, "-m", "src.visualization.build_chart_pack"]
    assert cwd == tmp_path
    assert check
    assert env["MPLBACKEND"] == "Agg"
    assert env["MPLCONFIGDIR"] == str(tmp_path / ".cache" / "matplotlib")


def test_pipeline_main_uses_the_canonical_synthetic_stage_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(pipeline, "run_step", lambda name, module: calls.append((name, module)))

    pipeline.main()

    assert [module for _name, module in calls] == [
        stage.module for stage in pipeline.build_pipeline_stages(PipelineProfile.SYNTHETIC)
    ]


def test_external_pipeline_requires_an_explicit_raw_data_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PIPELINE_PROFILE", "external")
    monkeypatch.delenv("RAW_DATA_DIR", raising=False)

    with pytest.raises(RuntimeError, match="RAW_DATA_DIR"):
        pipeline.main()


def test_external_pipeline_skips_generation_and_uses_canonical_labels(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, str]] = []
    stages = (
        StageSpec("validate_raw", "module.validate", (), 10, display_name="Validate raw"),
        StageSpec("analyze", "module.analyze", ("validate_raw",), 10, display_name="Analyze"),
    )
    monkeypatch.setenv("PIPELINE_PROFILE", "external")
    monkeypatch.setenv("RAW_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(pipeline, "build_pipeline_stages", lambda _profile: stages)
    monkeypatch.setattr(pipeline, "run_step", lambda name, module: calls.append((name, module)))

    pipeline.main()

    assert calls == [("Validate raw", "module.validate"), ("Analyze", "module.analyze")]


def test_raw_data_directory_resolves_relative_paths_and_active_bundles(tmp_path: Path) -> None:
    assert resolve_raw_data_dir({}) == PROJECT_ROOT / "data" / "raw"
    assert resolve_raw_data_dir({"RAW_DATA_DIR": "external/raw"}) == PROJECT_ROOT / "external/raw"

    active_bundle = tmp_path / "v1" / "bundles" / "bundle-1"
    active_bundle.mkdir(parents=True)
    (active_bundle / "manifest.json").write_text("{}", encoding="utf-8")
    (tmp_path / "v1" / "current.json").write_text(
        '{"bundle":"bundles/bundle-1","contract_version":"1.0.0"}',
        encoding="utf-8",
    )

    assert resolve_raw_data_dir({"RAW_DATA_DIR": str(tmp_path)}) == active_bundle

    (tmp_path / "v1" / "current.json").write_text(
        '{"bundle":"bundles/bundle-1","contract_version":"2.0.0"}',
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="incompatible raw-data contract"):
        resolve_raw_data_dir({"RAW_DATA_DIR": str(tmp_path)})
