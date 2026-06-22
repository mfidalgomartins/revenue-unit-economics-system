"""Unit tests for the governance data catalog."""

from __future__ import annotations

from src.governance.data_catalog import (
    FIELD_DEFINITIONS,
    LAYER_OWNER,
    _infer_role,
    build_data_catalog,
)


def test_infer_role_classifies_columns() -> None:
    assert _infer_role("customer_id", "object") == "identifier"
    assert _infer_role("signup_date", "datetime64[ns]") == "temporal"
    assert _infer_role("cohort_month", "datetime64[ns]") == "temporal"
    assert _infer_role("is_high_value", "bool") == "boolean"
    assert _infer_role("revenue", "float64") == "metric"
    assert _infer_role("transaction_count", "int64") == "metric"
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


def test_documented_fields_have_definition_and_use() -> None:
    catalog = build_data_catalog()
    documented = catalog[catalog["column"].isin(FIELD_DEFINITIONS)]
    assert (documented["definition"].str.len() > 0).all()
    assert (documented["business_use"].str.len() > 0).all()
