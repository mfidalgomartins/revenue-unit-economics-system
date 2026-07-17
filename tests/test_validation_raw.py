from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import src.validation.validate_raw_data as raw_validation
from src.ingestion.contracts import ContractViolation
from src.validation.validate_raw_data import RawDataValidationError, build_results


def _base_tables() -> dict[str, pd.DataFrame]:
    customers = pd.DataFrame(
        {
            "customer_id": ["C1", "C2"],
            "signup_date": pd.to_datetime(["2024-01-01", "2024-01-02"]),
            "segment": ["SMB", "Startup"],
            "region": ["EMEA", "APAC"],
            "acquisition_channel": ["organic", "paid_search"],
        }
    )
    transactions = pd.DataFrame(
        {
            "transaction_id": ["T1", "T2"],
            "customer_id": ["C1", "C2"],
            "transaction_date": pd.to_datetime(["2024-01-03", "2024-01-05"]),
            "revenue": [100.0, 120.0],
            "cost": [55.0, 80.0],
            "product_type": ["Core", "Premium"],
        }
    )
    marketing = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01", "2024-01-01"]),
            "acquisition_channel": ["organic", "paid_search"],
            "spend": [40.0, 60.0],
        }
    )
    touchpoints = pd.DataFrame(
        {
            "touchpoint_id": ["TP1", "TP2"],
            "customer_id": ["C1", "C2"],
            "touchpoint_date": pd.to_datetime(["2023-12-30", "2024-01-01"]),
            "acquisition_channel": ["organic", "paid_search"],
            "touchpoint_order": [1, 1],
            "is_conversion_touch": [True, True],
        }
    )
    experiments = pd.DataFrame(
        {
            "experiment_id": ["EXP1", "EXP1"],
            "customer_id": ["C1", "C2"],
            "acquisition_channel": ["paid_search", "paid_search"],
            "assignment": ["control", "treatment"],
            "assigned_date": pd.to_datetime(["2024-01-06", "2024-01-06"]),
            "outcome_window_days": [90, 90],
            "converted": [False, True],
            "pre_period_contribution": [40.0, 42.0],
            "observed_contribution": [0.0, 75.0],
        }
    )
    pricing_rows: list[dict[str, object]] = []
    intervention_id = 1
    for product in ("Core", "Add-on", "Premium", "Services"):
        for region in ("North America", "EMEA", "LATAM", "APAC"):
            for assignment, multiplier in (
                ("price_down_10", 0.9),
                ("control", 1.0),
                ("price_up_10", 1.1),
            ):
                pricing_rows.append(
                    {
                        "intervention_id": f"PI{intervention_id}",
                        "week_start": pd.Timestamp("2024-01-01"),
                        "product_type": product,
                        "region": region,
                        "assignment": assignment,
                        "reference_price": 100.0,
                        "observed_price": 100.0 * multiplier,
                        "units_sold": 10,
                        "revenue": 1000.0 * multiplier,
                        "contribution_margin": 400.0 * multiplier,
                    }
                )
                intervention_id += 1
    pricing = pd.DataFrame(pricing_rows)
    return {
        "customers": customers,
        "transactions": transactions,
        "marketing_spend": marketing,
        "marketing_touchpoints": touchpoints,
        "marketing_experiments": experiments,
        "pricing_interventions": pricing,
    }


def test_build_results_all_pass_for_clean_data() -> None:
    results = build_results(_base_tables())
    status_counts = results["status"].value_counts().to_dict()
    assert status_counts.get("FAIL", 0) == 0
    assert status_counts.get("WARN", 0) == 0


def test_build_results_accepts_signed_causal_contribution_outcomes() -> None:
    tables = _base_tables()
    tables["marketing_experiments"].loc[0, "pre_period_contribution"] = -10.0
    tables["marketing_experiments"].loc[1, "observed_contribution"] = -4.0
    tables["pricing_interventions"].loc[0, "contribution_margin"] = -50.0

    results = build_results(tables).set_index("check_name")

    assert results.loc["causal_design_input_integrity", "status"] == "PASS"


def test_raw_gate_verifies_normalized_bundle_integrity_when_manifest_is_present(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    verified: list[Path] = []
    monkeypatch.setattr(raw_validation, "RAW_DIR", tmp_path)
    monkeypatch.setattr(
        raw_validation,
        "verify_bundle",
        lambda path: verified.append(path),
        raising=False,
    )

    raw_validation._verify_bundle_if_present()
    assert verified == []

    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    raw_validation._verify_bundle_if_present()
    assert verified == [tmp_path]

    (tmp_path / "manifest.json").unlink()
    monkeypatch.setenv("PIPELINE_PROFILE", "external")
    with pytest.raises(ContractViolation, match="requires a verified bundle manifest"):
        raw_validation._verify_bundle_if_present()


def test_raw_gate_reports_bundle_integrity_failure_before_loading_tables(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    raw_dir = tmp_path / "bundle"
    output_dir = tmp_path / "outputs"
    raw_dir.mkdir()
    (raw_dir / "manifest.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(raw_validation, "RAW_DIR", raw_dir)
    monkeypatch.setattr(raw_validation, "OUT_TABLES_DIR", output_dir)

    def reject_bundle(_path: Path) -> None:
        raise ContractViolation("digest mismatch")

    monkeypatch.setattr(raw_validation, "verify_bundle", reject_bundle)

    with pytest.raises(RawDataValidationError, match="bundle_integrity"):
        raw_validation.run()

    summary = pd.read_csv(output_dir / "raw_validation_summary.csv")
    assert summary.to_dict(orient="records") == [
        {
            "check_name": "normalized_bundle_integrity",
            "status": "FAIL",
            "detail": "digest mismatch",
        }
    ]


def test_build_results_detects_key_failures() -> None:
    tables = _base_tables()
    tables["transactions"].loc[0, "customer_id"] = "C9"
    tables["transactions"].loc[1, "transaction_date"] = pd.Timestamp("2023-12-31")
    tables["transactions"].loc[1, "revenue"] = -2.0

    results = build_results(tables)
    by_check = results.set_index("check_name")

    assert by_check.loc["transaction_customer_referential_integrity", "status"] == "FAIL"
    assert by_check.loc["transaction_date_not_before_signup", "status"] == "FAIL"
    assert by_check.loc["value_range_sanity", "status"] == "FAIL"


def test_build_results_surfaces_negative_margin_transactions_for_review() -> None:
    tables = _base_tables()
    tables["transactions"].loc[0, "cost"] = 110.0

    results = build_results(tables).set_index("check_name")

    assert results.loc["negative_margin_transaction_review", "status"] == "WARN"


def test_build_results_accepts_small_negative_margin_exception_rate() -> None:
    tables = _base_tables()
    transactions = pd.concat([tables["transactions"]] * 100, ignore_index=True)
    transactions["transaction_id"] = [f"T{i}" for i in range(len(transactions))]
    transactions.loc[0, "cost"] = 110.0
    tables["transactions"] = transactions

    results = build_results(tables).set_index("check_name")

    assert results.loc["negative_margin_transaction_review", "status"] == "PASS"


def test_build_results_detects_channel_domain_mismatch() -> None:
    tables = _base_tables()
    tables["marketing_spend"].loc[1, "acquisition_channel"] = "social_ads"

    results = build_results(tables).set_index("check_name")

    assert results.loc["channel_domain_alignment", "status"] == "FAIL"


def test_build_results_rejects_unexpected_domains_and_nonfinite_values() -> None:
    tables = _base_tables()
    tables["customers"].loc[0, "segment"] = "Unknown"
    tables["transactions"].loc[0, "revenue"] = np.inf

    results = build_results(tables).set_index("check_name")

    assert results.loc["categorical_domain_values", "status"] == "FAIL"
    assert results.loc["contract_types_and_finite_values", "status"] == "FAIL"


def test_build_results_short_circuits_malformed_prerequisites() -> None:
    tables = _base_tables()
    tables["transactions"] = tables["transactions"].drop(columns="revenue")

    results = build_results(tables).set_index("check_name")

    assert results.loc["schema_columns_match", "status"] == "FAIL"
    assert "value_range_sanity" not in results.index


def test_run_writes_report_before_raising_on_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    tables = _base_tables()
    tables["transactions"].loc[0, "customer_id"] = "C9"
    monkeypatch.setattr(raw_validation, "load_raw_tables", lambda: tables)
    monkeypatch.setattr(raw_validation, "OUT_TABLES_DIR", tmp_path)

    with pytest.raises(RawDataValidationError, match="referential_integrity"):
        raw_validation.run()

    summary_path = tmp_path / "raw_validation_summary.csv"
    assert summary_path.exists()
    summary = pd.read_csv(summary_path)
    assert (summary["status"] == "FAIL").any()


def test_run_reports_missing_raw_file_before_raising(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    raw_dir = tmp_path / "raw"
    output_dir = tmp_path / "outputs"
    raw_dir.mkdir()
    tables = _base_tables()
    tables["customers"].to_csv(raw_dir / "customers.csv", index=False)
    tables["transactions"].to_csv(raw_dir / "transactions.csv", index=False)
    monkeypatch.setattr(raw_validation, "RAW_DIR", raw_dir)
    monkeypatch.setattr(raw_validation, "OUT_TABLES_DIR", output_dir)

    with pytest.raises(RawDataValidationError, match="required_tables_present"):
        raw_validation.run()

    summary = pd.read_csv(output_dir / "raw_validation_summary.csv")
    assert summary.loc[0, "check_name"] == "required_tables_present"
    assert summary.loc[0, "status"] == "FAIL"


def test_run_reports_unreadable_raw_file_before_raising(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    raw_dir = tmp_path / "raw"
    output_dir = tmp_path / "outputs"
    raw_dir.mkdir()
    tables = _base_tables()
    (raw_dir / "customers.csv").write_bytes(b"\xff\xfe\x00")
    for table_name, frame in tables.items():
        if table_name != "customers":
            frame.to_csv(raw_dir / f"{table_name}.csv", index=False)
    monkeypatch.setattr(raw_validation, "RAW_DIR", raw_dir)
    monkeypatch.setattr(raw_validation, "OUT_TABLES_DIR", output_dir)

    with pytest.raises(RawDataValidationError, match="raw_files_readable"):
        raw_validation.run()

    summary = pd.read_csv(output_dir / "raw_validation_summary.csv")
    assert summary.loc[0, "check_name"] == "raw_files_readable"
    assert summary.loc[0, "status"] == "FAIL"
