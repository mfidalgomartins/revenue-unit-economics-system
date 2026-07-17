from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
from src.governance.metric_registry import classify_channel_efficiency

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_raw_and_processed_metric_contracts() -> None:
    customers = pd.read_csv(PROJECT_ROOT / "data" / "raw" / "customers.csv")
    transactions = pd.read_csv(PROJECT_ROOT / "data" / "raw" / "transactions.csv")
    marketing = pd.read_csv(PROJECT_ROOT / "data" / "raw" / "marketing_spend.csv")
    customer_metrics = pd.read_csv(PROJECT_ROOT / "data" / "processed" / "customer_metrics.csv")
    monthly = pd.read_csv(PROJECT_ROOT / "outputs" / "tables" / "monthly_revenue_health.csv")

    assert len(customers) == 9000
    assert len(transactions) == 69950
    assert len(marketing) == 6576
    assert len(customer_metrics) == 9000
    assert len(monthly) == 36

    assert math.isclose(float(transactions["revenue"].sum()), 54595966.54, abs_tol=0.01)
    assert math.isclose(float(transactions["cost"].sum()), 38031935.87, abs_tol=0.01)
    assert math.isclose(float(customer_metrics["total_revenue"].sum()), 54595966.54, abs_tol=0.01)
    assert math.isclose(float(customer_metrics["total_cost"].sum()), 38031935.87, abs_tol=0.01)
    assert math.isclose(float(monthly["total_revenue"].sum()), 54595966.54, abs_tol=0.01)
    assert math.isclose(float(monthly["total_cost"].sum()), 38031935.87, abs_tol=0.01)


def test_unit_economics_classification_contract() -> None:
    unit_econ = pd.read_csv(PROJECT_ROOT / "data" / "processed" / "unit_economics.csv")
    observed = {
        row.acquisition_channel: classify_channel_efficiency(
            float(row.LTV_to_CAC),
            float(row.approximate_payback_period),
            str(row.payback_status),
        )
        for row in unit_econ.itertuples(index=False)
    }

    assert observed == {
        "email": "borderline",
        "organic": "efficient",
        "paid_search": "inefficient",
        "partners": "efficient",
        "referral": "efficient",
        "social_ads": "inefficient",
    }
