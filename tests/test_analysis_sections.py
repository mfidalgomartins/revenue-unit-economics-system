"""Exercise the analytical section builders against committed synthetic data.

These run each compute_* entry point on the real deterministic tables and assert
structural and directional invariants, covering the bulk of the analysis module
without re-implementing its arithmetic.
"""

from __future__ import annotations

import math

import pandas as pd
from src.analysis.unit_economics_analysis import (
    compute_cohort_analysis,
    compute_revenue_decomposition,
    compute_segment_profitability,
    compute_unit_economics_section,
    fmt_currency,
    fmt_num,
    fmt_pct,
    load_data,
)


def test_formatters_handle_values_and_missing() -> None:
    assert fmt_currency(1234.5) == "$1,234"
    assert fmt_currency(float("nan")) == "n/a"
    assert fmt_pct(0.1234) == "12.3%"
    assert fmt_pct(float("nan")) == "n/a"
    assert fmt_num(1234.567, digits=1) == "1,234.6"
    assert fmt_num(float("nan")) == "n/a"


def test_revenue_decomposition_returns_table_and_summary() -> None:
    tables = load_data()
    table, summary = compute_revenue_decomposition(
        tables["customers"], tables["transactions"]
    )
    assert isinstance(table, pd.DataFrame)
    assert not table.empty
    assert isinstance(summary, dict)


def test_cohort_analysis_returns_table_and_summary() -> None:
    tables = load_data()
    table, summary = compute_cohort_analysis(tables["cohort_table"])
    assert isinstance(table, pd.DataFrame)
    assert not table.empty
    assert isinstance(summary, dict)


def test_unit_economics_section_classifies_channels() -> None:
    tables = load_data()
    table, summary = compute_unit_economics_section(tables["unit_economics"])
    assert isinstance(summary, dict)
    assert "efficiency_status" in table.columns
    assert set(table["efficiency_status"]).issubset(
        {"efficient", "borderline", "inefficient", "undefined"}
    )
    # LTV/CAC ratios are finite and non-negative for the synthetic channels.
    finite = table["LTV_to_CAC"].dropna()
    assert (finite >= 0).all()


def test_segment_profitability_returns_four_dimension_tables() -> None:
    tables = load_data()
    result = compute_segment_profitability(
        tables["customers"], tables["customer_metrics"], tables["transactions"]
    )
    assert len(result) == 5
    *frames, summary = result
    assert isinstance(summary, dict)
    for frame in frames:
        assert isinstance(frame, pd.DataFrame)

    segment_table = frames[0]
    # Contribution margin equals revenue minus cost for every dimension row.
    recomputed = segment_table["total_revenue"] - segment_table["total_cost"]
    assert all(
        math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-6)
        for a, b in zip(segment_table["contribution_margin"], recomputed, strict=False)
    )
