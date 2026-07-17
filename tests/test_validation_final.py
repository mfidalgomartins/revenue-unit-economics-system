from __future__ import annotations

from pathlib import Path

import pytest
import src.validation.validate_final_outputs as final_validation


def _check_status(checks: list[final_validation.CheckResult], check_name: str) -> str:
    return next(check.status for check in checks if check.check_name == check_name)


def test_final_validation_passes_committed_analytical_outputs() -> None:
    checks, _issues, _caveats, gate_status = final_validation.run_checks(
        final_validation.load_data()
    )

    assert all(check.status != "FAIL" for check in checks)
    assert gate_status != final_validation.GATE_FAILED


def test_final_validation_rejects_large_negative_decomposition_residual() -> None:
    data = final_validation.load_data()
    decomposition = data["revenue_decomposition"].copy()
    total_change = abs(
        float(
            decomposition.loc[
                decomposition["effect"] == "total_revenue_change", "effect_value"
            ].iloc[0]
        )
    )
    decomposition.loc[decomposition["effect"] == "residual", "effect_value"] = -total_change
    data["revenue_decomposition"] = decomposition

    checks, _issues, _caveats, gate_status = final_validation.run_checks(data)

    assert _check_status(checks, "decomposition_consistency_check") == "FAIL"
    assert gate_status == final_validation.GATE_FAILED


def test_final_validation_rejects_missing_dashboard(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(final_validation, "PROJECT_ROOT", tmp_path)

    checks, _issues, _caveats, gate_status = final_validation.run_checks(
        final_validation.load_data()
    )

    assert _check_status(checks, "dashboard_presence") == "FAIL"
    assert _check_status(checks, "dashboard_deterministic_metadata") == "FAIL"
    assert _check_status(checks, "dashboard_size_budget_mb") == "FAIL"
    assert gate_status == final_validation.GATE_FAILED


def test_final_validation_rejects_large_but_corrupt_pdf(
    monkeypatch,
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "revenue_unit_economics_report.pdf"
    report_path.write_bytes(b"not-a-pdf" * 20_000)
    monkeypatch.setattr(final_validation, "REPORTS_DIR", tmp_path)

    checks, _issues, _caveats, gate_status = final_validation.run_checks(
        final_validation.load_data()
    )

    assert _check_status(checks, "analytical_report_presence") == "PASS"
    assert _check_status(checks, "analytical_report_integrity") == "FAIL"
    assert gate_status == final_validation.GATE_FAILED


def test_final_validation_rejects_out_of_bounds_cohort_rate() -> None:
    data = final_validation.load_data()
    cohort = data["cohort_table"].copy()
    cohort.loc[cohort.index[0], "signup_activity_rate"] = 1.01
    data["cohort_table"] = cohort

    checks, _issues, _caveats, gate_status = final_validation.run_checks(data)

    assert _check_status(checks, "cohort_activation_and_retention_bounds") == "FAIL"
    assert gate_status == final_validation.GATE_FAILED


def test_final_validation_rejects_negative_scenario_spend() -> None:
    data = final_validation.load_data()
    plan = data["scenario_plan"].copy()
    plan.loc[plan.index[0], "scenario_spend"] = -1.0
    data["scenario_plan"] = plan

    checks, _issues, _caveats, gate_status = final_validation.run_checks(data)

    assert _check_status(checks, "scenario_spend_nonnegative_and_finite") == "FAIL"
    assert gate_status == final_validation.GATE_FAILED


def test_final_validation_rejects_duplicate_and_nonfinite_seed_results() -> None:
    data = final_validation.load_data()
    sensitivity = data["seed_sensitivity"].copy()
    sensitivity.loc[sensitivity.index[-1], "seed"] = sensitivity.loc[sensitivity.index[0], "seed"]
    sensitivity.loc[sensitivity.index[0], "estimated_contribution_uplift"] = float("inf")
    data["seed_sensitivity"] = sensitivity

    checks, _issues, _caveats, gate_status = final_validation.run_checks(data)

    assert _check_status(checks, "scenario_seed_sensitivity_coverage") == "FAIL"
    assert _check_status(checks, "scenario_seed_sensitivity_values_finite") == "FAIL"
    assert gate_status == final_validation.GATE_FAILED


def test_final_validation_rejects_missing_governance_publications(
    monkeypatch,
    tmp_path: Path,
) -> None:
    data = final_validation.load_data()
    monkeypatch.setattr(final_validation, "REPORTS_DIR", tmp_path)

    checks, _issues, _caveats, gate_status = final_validation.run_checks(data)

    assert _check_status(checks, "metric_registry_integrity") == "FAIL"
    assert _check_status(checks, "decision_brief_integrity") == "FAIL"
    assert _check_status(checks, "analytical_report_integrity") == "FAIL"
    assert gate_status == final_validation.GATE_FAILED


def test_read_png_dimensions_rejects_invalid_header(tmp_path: Path) -> None:
    invalid_png = tmp_path / "invalid.png"
    invalid_png.write_bytes(b"not-a-png")

    with pytest.raises(ValueError, match="Invalid PNG header"):
        final_validation.read_png_dimensions(invalid_png)
