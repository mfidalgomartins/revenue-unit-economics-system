from __future__ import annotations

import pandas as pd
from src.validation.validate_raw_data import build_results


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
    return {
        "customers": customers,
        "transactions": transactions,
        "marketing_spend": marketing,
    }


def test_build_results_all_pass_for_clean_data() -> None:
    results = build_results(_base_tables())
    status_counts = results["status"].value_counts().to_dict()
    assert status_counts.get("FAIL", 0) == 0
    assert status_counts.get("WARN", 0) == 0


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
