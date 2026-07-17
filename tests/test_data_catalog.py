"""Unit tests for the governance data catalog."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from src.governance.data_catalog import (
    DATASETS,
    FIELD_DEFINITIONS,
    LAYER_OWNER,
    _infer_role,
    _validate_field_definitions,
    build_data_catalog,
)
from src.paths import PROJECT_ROOT


def test_infer_role_classifies_columns() -> None:
    assert _infer_role("customer_id", "object") == "identifier"
    assert _infer_role("signup_date", "datetime64[ns]") == "temporal"
    assert _infer_role("cohort_month", "datetime64[ns]") == "temporal"
    assert _infer_role("is_high_value", "bool") == "boolean"
    assert _infer_role("payback_is_censored", "bool") == "boolean"
    assert _infer_role("revenue", "float64") == "metric"
    assert _infer_role("transaction_count", "int64") == "metric"
    assert _infer_role("months_since_cohort", "int64") == "metric"
    assert _infer_role("payback_horizon_months", "int64") == "metric"
    assert _infer_role("segment", "object") == "dimension"


def test_build_data_catalog_has_expected_shape_and_owners() -> None:
    catalog = build_data_catalog()

    assert not catalog.empty
    assert list(catalog.columns) == [
        "layer",
        "dataset",
        "column",
        "dtype",
        "role",
        "owner",
        "definition",
        "business_use",
    ]
    # Owners are resolved from the layer map for every row.
    assert set(catalog["owner"]).issubset(set(LAYER_OWNER.values()))
    assert set(catalog["layer"]).issubset(set(LAYER_OWNER))
    # Sorted by layer, dataset, column for stable diffs.
    assert catalog[["layer", "dataset", "column"]].apply(tuple, axis=1).is_monotonic_increasing


def test_catalog_covers_every_pre_qa_csv_schema() -> None:
    catalog = build_data_catalog()

    excluded_outputs = {"data_catalog", "qa_checks", "qa_issues"}
    source_files = [
        *sorted((PROJECT_ROOT / "data" / "raw").glob("*.csv")),
        *sorted((PROJECT_ROOT / "data" / "processed").glob("*.csv")),
        *sorted((PROJECT_ROOT / "outputs" / "tables").glob("*.csv")),
    ]
    expected_datasets = {path.stem for path in source_files if path.stem not in excluded_outputs}
    configured_datasets = {dataset for _, dataset, _ in DATASETS}

    assert configured_datasets == expected_datasets
    assert set(catalog["dataset"]) == expected_datasets

    expected_row_count = 0
    for _, dataset, path in DATASETS:
        expected_columns = set(pd.read_csv(path, nrows=0).columns)
        catalog_columns = set(catalog.loc[catalog["dataset"] == dataset, "column"])
        assert catalog_columns == expected_columns
        expected_row_count += len(expected_columns)
    assert len(catalog) == expected_row_count


def test_every_catalog_field_has_nonblank_definition_and_use() -> None:
    catalog = build_data_catalog()

    assert set(catalog["column"]) == set(FIELD_DEFINITIONS)
    assert catalog["definition"].str.strip().ne("").all()
    assert catalog["business_use"].str.strip().ne("").all()


def test_catalog_uses_current_governed_semantics() -> None:
    current_fields = {
        "transaction_span_days",
        "revenue_per_transaction_span_day",
        "cohort_size",
        "month_0_active_customers",
        "retained_month_0_customers",
        "late_activation_customers",
        "month_0_activation_rate",
        "signup_activity_rate",
        "retained_from_month_0_rate",
        "median_month_0_activation_rate",
        "median_signup_activity_rate",
        "median_retained_from_month_0_rate",
        "payback_status",
        "payback_is_censored",
        "payback_horizon_months",
        "payback_mature_customers",
        "payback_mature_customer_share",
        "payback_horizon_contribution_per_customer",
        "allocation_score",
        "efficient_channels_selected",
        "inefficient_channels_selected",
    }
    retired_fields = {
        "lifetime_days",
        "revenue_per_day",
        "median_activity_retention",
        "efficient_channels_after_policy",
        "inefficient_channels_after_policy",
    }

    assert current_fields.issubset(FIELD_DEFINITIONS)
    assert retired_fields.isdisjoint(FIELD_DEFINITIONS)


def test_field_definition_validation_rejects_missing_and_blank_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match=r"missing=.*undocumented_field"):
        _validate_field_definitions({"undocumented_field"})

    monkeypatch.setitem(FIELD_DEFINITIONS, "blank_field", ("", "Business use."))
    with pytest.raises(ValueError, match=r"blank=.*blank_field"):
        _validate_field_definitions({"blank_field"})


def test_catalog_dataset_paths_are_unique() -> None:
    paths = [Path(path) for _, _, path in DATASETS]
    dataset_names = [dataset for _, dataset, _ in DATASETS]

    assert len(paths) == len(set(paths))
    assert len(dataset_names) == len(set(dataset_names))
