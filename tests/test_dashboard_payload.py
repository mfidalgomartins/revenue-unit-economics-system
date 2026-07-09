from __future__ import annotations

import pandas as pd
from src.dashboard_builder.build_dashboard_assets import (
    build_dashboard_html,
    build_embedded_payload,
)


def test_dashboard_payload_contains_policy_and_no_volatile_timestamp() -> None:
    customers = pd.DataFrame(
        {
            "customer_id": ["C1"],
            "signup_date": pd.to_datetime(["2024-01-01"]),
            "segment": ["SMB"],
            "region": ["EMEA"],
            "acquisition_channel": ["organic"],
        }
    )
    transactions = pd.DataFrame(
        {
            "transaction_id": ["T1"],
            "customer_id": ["C1"],
            "transaction_date": pd.to_datetime(["2024-01-02"]),
            "revenue": [100.0],
            "cost": [60.0],
            "product_type": ["Core"],
        }
    )
    marketing = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01"]),
            "acquisition_channel": ["organic"],
            "spend": [30.0],
        }
    )

    payload = build_embedded_payload(customers, transactions, marketing)
    meta = payload["meta"]

    assert "metric_policy" in meta
    assert "generated_at" not in meta
    assert "data_fingerprint" in meta


def test_payload_columnar_encoding_round_trips() -> None:
    customers = pd.DataFrame(
        {
            "customer_id": ["C1", "C2"],
            "signup_date": pd.to_datetime(["2024-01-01", "2024-02-10"]),
            "segment": ["SMB", "Enterprise"],
            "region": ["EMEA", "APAC"],
            "acquisition_channel": ["organic", "referral"],
        }
    )
    transactions = pd.DataFrame(
        {
            "transaction_id": ["T1", "T2"],
            "customer_id": ["C2", "C1"],
            "transaction_date": pd.to_datetime(["2024-02-11", "2024-01-02"]),
            "revenue": [250.0, 100.0],
            "cost": [90.0, 60.0],
            "product_type": ["Premium", "Core"],
        }
    )
    marketing = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01"]),
            "acquisition_channel": ["referral"],
            "spend": [30.0],
        }
    )

    payload = build_embedded_payload(customers, transactions, marketing)
    values = payload["meta"]["values"]

    # Dates are integer day offsets from the Unix epoch.
    epoch = pd.Timestamp("1970-01-01")
    assert payload["customers"]["sd"] == [
        (pd.Timestamp("2024-01-01") - epoch).days,
        (pd.Timestamp("2024-02-10") - epoch).days,
    ]
    # Dimensions are indexes into the sorted meta.values lists.
    assert [values["segments"][i] for i in payload["customers"]["seg"]] == ["SMB", "Enterprise"]
    assert [values["regions"][i] for i in payload["customers"]["reg"]] == ["EMEA", "APAC"]
    # Transactions reference customers by row index, in input order.
    assert payload["transactions"]["ci"] == [1, 0]
    assert [values["product_types"][i] for i in payload["transactions"]["prod"]] == [
        "Premium",
        "Core",
    ]
    assert payload["transactions"]["rev"] == [250.0, 100.0]
    assert payload["marketing_spend"]["spend"] == [30.0]
    assert payload["meta"]["coverage_start"] == "2024-01-01"
    assert payload["meta"]["coverage_end"] == "2024-02-11"


def test_dashboard_html_contains_decision_layer_and_contract_ltv_logic() -> None:
    customers = pd.DataFrame(
        {
            "customer_id": ["C1"],
            "signup_date": pd.to_datetime(["2024-01-01"]),
            "segment": ["SMB"],
            "region": ["EMEA"],
            "acquisition_channel": ["organic"],
        }
    )
    transactions = pd.DataFrame(
        {
            "transaction_id": ["T1"],
            "customer_id": ["C1"],
            "transaction_date": pd.to_datetime(["2024-01-02"]),
            "revenue": [100.0],
            "cost": [60.0],
            "product_type": ["Core"],
        }
    )
    marketing = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01"]),
            "acquisition_channel": ["organic"],
            "spend": [30.0],
        }
    )

    html = build_dashboard_html(build_embedded_payload(customers, transactions, marketing))

    assert 'id="decision-command"' in html
    assert 'class="chart-insight"' in html
    assert "const avgLTV = cCount > 0 ? cm / cCount : NaN;" in html
    assert "Full-coverage observed LTV versus CAC. Only the channel filter applies." in html
    assert "label: 'Active Customers'" in html
    assert "label: 'Customers Acquired'" in html
    assert "Revenue is outpacing cost; monitor whether margin leverage persists." in html
    assert "Cost is growing faster; investigate operating leverage." in html
    assert "function escapeHtml(value)" in html
    assert "fonts.googleapis.com" not in html
    assert "acquiredCm" not in html
