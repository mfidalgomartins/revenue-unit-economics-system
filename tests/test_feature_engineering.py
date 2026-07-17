from __future__ import annotations

import math

import pandas as pd
from src.feature_engineering.build_features import (
    build_cohort_table,
    build_customer_metrics,
    build_unit_economics,
)


def test_build_customer_metrics_computes_expected_fields() -> None:
    customers = pd.DataFrame(
        {
            "customer_id": ["C1", "C2"],
            "signup_date": pd.to_datetime(["2024-01-01", "2024-01-05"]),
            "segment": ["Startup", "SMB"],
            "region": ["EMEA", "North America"],
            "acquisition_channel": ["paid_search", "organic"],
        }
    )
    transactions = pd.DataFrame(
        {
            "transaction_id": ["T1", "T2"],
            "customer_id": ["C1", "C1"],
            "transaction_date": pd.to_datetime(["2024-01-10", "2024-01-15"]),
            "revenue": [100.0, 300.0],
            "cost": [60.0, 150.0],
            "product_type": ["Core", "Premium"],
        }
    )

    out = build_customer_metrics(customers, transactions)
    c1 = out.loc[out["customer_id"] == "C1"].iloc[0]
    c2 = out.loc[out["customer_id"] == "C2"].iloc[0]

    assert c1["total_revenue"] == 400.0
    assert c1["total_cost"] == 210.0
    assert c1["contribution_margin"] == 190.0
    assert math.isclose(c1["contribution_margin_pct"], 0.475, rel_tol=0, abs_tol=1e-6)
    assert c1["transaction_count"] == 2
    assert c1["transaction_span_days"] == 6
    assert c1["avg_revenue_per_transaction"] == 200.0
    assert math.isclose(c1["revenue_per_transaction_span_day"], 66.67, rel_tol=0, abs_tol=0.01)

    assert c2["transaction_count"] == 0
    assert c2["total_revenue"] == 0.0
    assert c2["total_cost"] == 0.0
    assert c2["transaction_span_days"] == 0
    assert c2["contribution_margin"] == 0.0


def test_build_unit_economics_handles_positive_and_negative_payback() -> None:
    customers = pd.DataFrame(
        {
            "customer_id": ["C1", "C2", "C3", "C4"],
            "signup_date": pd.to_datetime(["2022-01-01"] * 4),
            "segment": ["Startup", "SMB", "SMB", "Startup"],
            "region": ["EMEA", "EMEA", "EMEA", "EMEA"],
            "acquisition_channel": ["paid_search", "organic", "organic", "social_ads"],
        }
    )

    marketing_spend = pd.DataFrame(
        {
            "date": pd.to_datetime(
                [
                    "2022-01-01",
                    "2022-02-01",
                    "2024-02-01",
                    "2022-01-01",
                    "2022-02-01",
                    "2024-02-01",
                    "2022-01-01",
                    "2022-02-01",
                    "2024-02-01",
                ]
            ),
            "acquisition_channel": [
                "paid_search",
                "paid_search",
                "paid_search",
                "organic",
                "organic",
                "organic",
                "social_ads",
                "social_ads",
                "social_ads",
            ],
            "spend": [100.0, 100.0, 0.0, 60.0, 60.0, 0.0, 50.0, 50.0, 0.0],
        }
    )

    transactions = pd.DataFrame(
        {
            "transaction_id": ["T1", "T2", "T3", "T4"],
            "customer_id": ["C1", "C2", "C3", "C4"],
            "transaction_date": pd.to_datetime(
                ["2022-01-10", "2022-02-05", "2022-02-06", "2022-01-20"]
            ),
            "revenue": [300.0, 200.0, 150.0, 100.0],
            "cost": [100.0, 80.0, 70.0, 110.0],
            "product_type": ["Core", "Core", "Core", "Core"],
        }
    )
    customer_metrics = build_customer_metrics(customers, transactions)

    out = build_unit_economics(
        customers,
        marketing_spend,
        customer_metrics,
        transactions,
    )

    paid = out.loc[out["acquisition_channel"] == "paid_search"].iloc[0]
    organic = out.loc[out["acquisition_channel"] == "organic"].iloc[0]
    social = out.loc[out["acquisition_channel"] == "social_ads"].iloc[0]

    assert math.isclose(paid["CAC"], 200.0, rel_tol=0, abs_tol=1e-4)
    assert math.isclose(paid["average_LTV"], 200.0, rel_tol=0, abs_tol=1e-4)
    assert math.isclose(paid["total_channel_contribution_margin"], 200.0, rel_tol=0, abs_tol=1e-4)
    assert math.isclose(paid["LTV_to_CAC"], 1.0, rel_tol=0, abs_tol=1e-4)
    assert math.isclose(paid["payback_cac"], 100.0, rel_tol=0, abs_tol=1e-4)
    assert paid["approximate_payback_period"] == 0.0
    assert paid["payback_status"] == "recovered"

    assert math.isclose(organic["CAC"], 60.0, rel_tol=0, abs_tol=1e-4)
    assert math.isclose(organic["average_LTV"], 100.0, rel_tol=0, abs_tol=1e-4)
    assert math.isclose(
        organic["total_channel_contribution_margin"], 200.0, rel_tol=0, abs_tol=1e-4
    )
    assert math.isclose(organic["LTV_to_CAC"], 1.6667, rel_tol=0, abs_tol=1e-4)
    assert math.isclose(organic["payback_cac"], 30.0, rel_tol=0, abs_tol=1e-4)
    assert organic["approximate_payback_period"] == 1.0
    assert organic["payback_status"] == "recovered"

    assert math.isnan(float(social["approximate_payback_period"]))
    assert social["payback_status"] == "not_recovered"
    assert bool(social["payback_is_censored"])
    assert paid["payback_horizon_months"] == 24
    assert paid["payback_mature_customers"] == 1


def test_build_unit_economics_marks_channels_without_mature_customers() -> None:
    customers = pd.DataFrame(
        {
            "customer_id": ["C1"],
            "signup_date": pd.to_datetime(["2024-01-01"]),
            "segment": ["SMB"],
            "region": ["EMEA"],
            "acquisition_channel": ["organic"],
        }
    )
    marketing_spend = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-02-01"]),
            "acquisition_channel": ["organic"],
            "spend": [100.0],
        }
    )
    customer_metrics = pd.DataFrame(
        {
            "acquisition_channel": ["organic"],
            "contribution_margin": [0.0],
        }
    )
    transactions = pd.DataFrame(
        {
            "transaction_id": pd.Series(dtype="str"),
            "customer_id": pd.Series(dtype="str"),
            "transaction_date": pd.Series(dtype="datetime64[ns]"),
            "revenue": pd.Series(dtype="float64"),
            "cost": pd.Series(dtype="float64"),
            "product_type": pd.Series(dtype="str"),
        }
    )

    row = build_unit_economics(
        customers,
        marketing_spend,
        customer_metrics,
        transactions,
    ).iloc[0]

    assert row["payback_status"] == "insufficient_maturity"
    assert row["payback_mature_customers"] == 0
    assert math.isnan(float(row["approximate_payback_period"]))
    assert not bool(row["payback_is_censored"])


def test_build_cohort_table_fills_inactive_months_with_zero() -> None:
    customers = pd.DataFrame(
        {
            "customer_id": ["C1", "C2"],
            "signup_date": pd.to_datetime(["2024-01-01", "2024-03-01"]),
            "segment": ["SMB", "SMB"],
            "region": ["EMEA", "EMEA"],
            "acquisition_channel": ["organic", "organic"],
        }
    )
    transactions = pd.DataFrame(
        {
            "transaction_id": ["T1", "T2"],
            "customer_id": ["C1", "C2"],
            "transaction_date": pd.to_datetime(["2024-01-10", "2024-03-10"]),
            "revenue": [100.0, 50.0],
            "cost": [50.0, 25.0],
            "product_type": ["Core", "Core"],
        }
    )

    cohort = build_cohort_table(customers, transactions)
    jan_m2 = cohort.loc[
        (cohort["cohort_month"] == pd.Timestamp("2024-01-01"))
        & (cohort["activity_month"] == pd.Timestamp("2024-03-01"))
    ].iloc[0]

    assert jan_m2["customers_active"] == 0
    assert jan_m2["cohort_size"] == 1
    assert jan_m2["retained_month_0_customers"] == 0
    assert jan_m2["signup_activity_rate"] == 0.0
    assert jan_m2["retained_from_month_0_rate"] == 0.0
    assert jan_m2["cohort_revenue"] == 0.0
    assert jan_m2["average_revenue_per_active_customer"] == 0.0


def test_build_cohort_table_separates_activation_retention_and_late_activation() -> None:
    customers = pd.DataFrame(
        {
            "customer_id": ["C1", "C2", "C3"],
            "signup_date": pd.to_datetime(["2024-01-01"] * 3),
            "segment": ["SMB"] * 3,
            "region": ["EMEA"] * 3,
            "acquisition_channel": ["organic"] * 3,
        }
    )
    transactions = pd.DataFrame(
        {
            "transaction_id": ["T1", "T2", "T3", "T4"],
            "customer_id": ["C1", "C2", "C1", "C3"],
            "transaction_date": pd.to_datetime(
                ["2024-01-05", "2024-01-06", "2024-02-05", "2024-02-06"]
            ),
            "revenue": [100.0] * 4,
            "cost": [50.0] * 4,
            "product_type": ["Core"] * 4,
        }
    )

    cohort = build_cohort_table(customers, transactions)
    month_1 = cohort.loc[
        (cohort["cohort_month"] == pd.Timestamp("2024-01-01"))
        & (cohort["activity_month"] == pd.Timestamp("2024-02-01"))
    ].iloc[0]

    assert month_1["cohort_size"] == 3
    assert month_1["month_0_active_customers"] == 2
    assert month_1["customers_active"] == 2
    assert month_1["retained_month_0_customers"] == 1
    assert month_1["late_activation_customers"] == 1
    assert month_1["month_0_activation_rate"] == 0.666667
    assert month_1["signup_activity_rate"] == 0.666667
    assert month_1["retained_from_month_0_rate"] == 0.5
