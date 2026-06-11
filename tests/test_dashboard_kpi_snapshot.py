from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

from src.dashboard_builder.kpi_snapshot import compute_kpi_snapshot


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_kpi_snapshot_contract_full_coverage() -> None:
    customers = pd.read_csv(
        PROJECT_ROOT / "data" / "raw" / "customers.csv", parse_dates=["signup_date"]
    )
    transactions = pd.read_csv(
        PROJECT_ROOT / "data" / "raw" / "transactions.csv",
        parse_dates=["transaction_date"],
    )
    coverage_start = transactions["transaction_date"].min()
    coverage_end = transactions["transaction_date"].max()

    snapshot = compute_kpi_snapshot(
        customers=customers,
        transactions=transactions,
        start_date=coverage_start,
        end_date=coverage_end,
    )

    assert snapshot["growth_method"] == "first_vs_last_month"
    assert math.isclose(float(snapshot["revenue"]), 54595966.54, abs_tol=0.01)
    assert math.isclose(float(snapshot["margin"]), 16564030.67, abs_tol=0.01)
    assert snapshot["active_customer_count"] == 8157.0
    assert snapshot["acquired_customer_count"] == 8994.0
    assert snapshot["transaction_count"] == 69950.0
    assert math.isclose(float(snapshot["growth_rate"]), 46.777783980127055, abs_tol=1e-12)
