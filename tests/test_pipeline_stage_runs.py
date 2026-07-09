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
import src.scenario_engine.build_scenarios as scenarios
import src.validation.validate_raw_data as validate_raw


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


def test_validate_raw_run_writes_summary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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
