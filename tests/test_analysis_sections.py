"""Exercise the analytical section builders against committed synthetic data.

These run each compute_* entry point on the real deterministic tables and assert
structural and directional invariants, covering the bulk of the analysis module
without re-implementing its arithmetic.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest
from src.analysis.unit_economics_analysis import (
    compute_cohort_analysis,
    compute_overall_revenue_health,
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


def test_revenue_health_names_compound_monthly_growth_correctly() -> None:
    tables = load_data()
    _monthly, summary = compute_overall_revenue_health(tables["transactions"])

    assert "compound monthly revenue growth" in str(summary["result"])
    assert "CAGR" not in str(summary["result"])


def test_revenue_decomposition_effects_are_exhaustive_and_volume_led() -> None:
    tables = load_data()
    table, summary = compute_revenue_decomposition(tables["customers"], tables["transactions"])
    effects = table.set_index("effect")

    # The three effects fully account for the change: zero residual and
    # shares that sum to one.
    assert effects.loc["residual", "effect_value"] == pytest.approx(0.0, abs=1e-6)
    component_shares = effects.loc[
        ["customer_volume_effect", "average_revenue_effect", "mix_effect"],
        "share_of_total_change",
    ].sum()
    assert component_shares == pytest.approx(1.0, abs=1e-6)
    # Golden values on the committed deterministic seed (regression guard).
    assert effects.loc["customer_volume_effect", "share_of_total_change"] == pytest.approx(
        0.685957, abs=1e-4
    )
    assert effects.loc["total_revenue_change", "effect_value"] == pytest.approx(
        15_087_947.54, rel=1e-6
    )
    assert isinstance(summary, dict)


def test_cohort_analysis_medians_and_expansion_share() -> None:
    tables = load_data()
    table, summary = compute_cohort_analysis(tables["cohort_table"])
    at = table.set_index("months_since_cohort")

    # Revenue is indexed to month 0, while activity retention follows only
    # customers who were active in month 0; both stay bounded and decline.
    assert at.loc[0, "median_revenue_retention"] == pytest.approx(1.0)
    assert at.loc[0, "median_retained_from_month_0_rate"] == pytest.approx(1.0)
    assert at.loc[0, "median_month_0_activation_rate"] == pytest.approx(0.521554, abs=1e-4)
    assert at.loc[6, "median_signup_activity_rate"] == pytest.approx(0.344898, abs=1e-4)
    assert at.loc[6, "median_retained_from_month_0_rate"] == pytest.approx(0.359579, abs=1e-4)
    assert (table["median_retained_from_month_0_rate"].dropna() <= 1.0).all()
    assert (
        at.loc[3, "median_revenue_retention"]
        > at.loc[6, "median_revenue_retention"]
        > at.loc[12, "median_revenue_retention"]
    )
    # Golden values on the committed deterministic seed (regression guard).
    assert at.loc[6, "median_revenue_retention"] == pytest.approx(0.682916, abs=1e-4)
    assert at.loc[6, "revenue_expansion_share_m6"] == pytest.approx(1 / 6, abs=1e-4)
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
