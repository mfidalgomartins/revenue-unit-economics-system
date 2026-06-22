from __future__ import annotations

import math

import pandas as pd
from src.analysis.unit_economics_analysis import (
    compute_overall_revenue_health,
    safe_pct_change,
)


def test_safe_pct_change_handles_zero_base() -> None:
    assert math.isnan(safe_pct_change(100.0, 0.0))
    assert math.isclose(safe_pct_change(120.0, 100.0), 0.2, rel_tol=0, abs_tol=1e-12)


def test_compute_overall_revenue_health_builds_monthly_metrics() -> None:
    rows: list[dict[str, object]] = []
    for i, month in enumerate(pd.date_range("2024-01-01", "2024-12-01", freq="MS")):
        rows.append(
            {
                "transaction_id": f"T{i + 1}",
                "customer_id": "C1" if i % 2 == 0 else "C2",
                "transaction_date": month + pd.Timedelta(days=3),
                "revenue": 1000 + 100 * i,
                "cost": 600 + 50 * i,
                "product_type": "Core",
            }
        )
    transactions = pd.DataFrame(rows)

    monthly, result = compute_overall_revenue_health(transactions)

    assert len(monthly) == 12
    assert {"total_revenue", "total_cost", "contribution_margin", "contribution_margin_pct"}.issubset(monthly.columns)
    assert monthly["contribution_margin"].min() > 0
    assert "Average monthly revenue increased" in result["result"]
