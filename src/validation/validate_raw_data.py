"""Validate raw source tables before profiling and feature engineering."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
OUT_TABLES_DIR = PROJECT_ROOT / "outputs" / "tables"
NEGATIVE_MARGIN_REVIEW_THRESHOLD = 0.01


def load_raw_tables() -> dict[str, pd.DataFrame]:
    return {
        "customers": pd.read_csv(RAW_DIR / "customers.csv", parse_dates=["signup_date"]),
        "transactions": pd.read_csv(
            RAW_DIR / "transactions.csv", parse_dates=["transaction_date"]
        ),
        "marketing_spend": pd.read_csv(
            RAW_DIR / "marketing_spend.csv", parse_dates=["date"]
        ),
    }


def add_result(
    rows: list[dict[str, str]],
    check_name: str,
    status: str,
    detail: str,
) -> None:
    rows.append({"check_name": check_name, "status": status, "detail": detail})


def build_results(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    customers = tables["customers"]
    transactions = tables["transactions"]
    marketing = tables["marketing_spend"]

    results: list[dict[str, str]] = []

    add_result(
        results,
        "table_row_count_non_zero",
        "PASS"
        if len(customers) > 0 and len(transactions) > 0 and len(marketing) > 0
        else "FAIL",
        (
            f"customers={len(customers):,}, transactions={len(transactions):,}, "
            f"marketing_spend={len(marketing):,}"
        ),
    )

    expected_columns = {
        "customers": {
            "customer_id",
            "signup_date",
            "segment",
            "region",
            "acquisition_channel",
        },
        "transactions": {
            "transaction_id",
            "customer_id",
            "transaction_date",
            "revenue",
            "cost",
            "product_type",
        },
        "marketing_spend": {"date", "acquisition_channel", "spend"},
    }

    schema_ok = all(
        set(tables[name].columns) == expected_columns[name] for name in expected_columns
    )
    schema_detail = "; ".join(
        f"{name}={list(tables[name].columns)}" for name in ("customers", "transactions", "marketing_spend")
    )
    add_result(results, "schema_columns_match", "PASS" if schema_ok else "FAIL", schema_detail)

    raw_nulls = int(customers.isna().sum().sum() + transactions.isna().sum().sum() + marketing.isna().sum().sum())
    add_result(
        results,
        "null_values_raw_tables",
        "PASS" if raw_nulls == 0 else "FAIL",
        f"total_raw_nulls={raw_nulls}",
    )

    dup_customer = int(customers.duplicated(subset=["customer_id"]).sum())
    dup_transaction = int(transactions.duplicated(subset=["transaction_id"]).sum())
    dup_marketing = int(marketing.duplicated(subset=["date", "acquisition_channel"]).sum())
    duplicate_status = "PASS" if dup_customer == 0 and dup_transaction == 0 and dup_marketing == 0 else "FAIL"
    add_result(
        results,
        "grain_key_uniqueness",
        duplicate_status,
        (
            f"duplicate customer_id={dup_customer}, duplicate transaction_id={dup_transaction}, "
            f"duplicate date+channel={dup_marketing}"
        ),
    )

    orphan_transactions = int((~transactions["customer_id"].isin(customers["customer_id"])).sum())
    add_result(
        results,
        "transaction_customer_referential_integrity",
        "PASS" if orphan_transactions == 0 else "FAIL",
        f"orphan_transaction_rows={orphan_transactions}",
    )

    tx_join = transactions.merge(
        customers[["customer_id", "signup_date"]],
        on="customer_id",
        how="left",
    )
    tx_before_signup = int((tx_join["transaction_date"] < tx_join["signup_date"]).sum())
    add_result(
        results,
        "transaction_date_not_before_signup",
        "PASS" if tx_before_signup == 0 else "FAIL",
        f"rows_with_transaction_before_signup={tx_before_signup}",
    )

    non_positive_revenue = int((transactions["revenue"] <= 0).sum())
    negative_cost = int((transactions["cost"] < 0).sum())
    cost_above_revenue = int((transactions["cost"] > transactions["revenue"]).sum())
    negative_spend = int((marketing["spend"] < 0).sum())
    status_value_ranges = "PASS" if non_positive_revenue == 0 and negative_cost == 0 and negative_spend == 0 else "FAIL"
    add_result(
        results,
        "value_range_sanity",
        status_value_ranges,
        (
            f"non_positive_revenue={non_positive_revenue}, "
            f"negative_cost={negative_cost}, negative_spend={negative_spend}"
        ),
    )

    negative_margin_rate = cost_above_revenue / len(transactions)
    add_result(
        results,
        "negative_margin_transaction_review",
        "WARN" if negative_margin_rate > NEGATIVE_MARGIN_REVIEW_THRESHOLD else "PASS",
        (
            f"rows_with_cost_above_revenue={cost_above_revenue}, "
            f"share={negative_margin_rate:.2%}, "
            f"review_threshold={NEGATIVE_MARGIN_REVIEW_THRESHOLD:.2%}"
        ),
    )

    channels = sorted(customers["acquisition_channel"].dropna().unique())
    marketing_channels = sorted(marketing["acquisition_channel"].dropna().unique())
    add_result(
        results,
        "channel_domain_alignment",
        "PASS" if channels == marketing_channels else "FAIL",
        f"customer_channels={channels}, marketing_channels={marketing_channels}",
    )

    expected_pairs = (
        len(pd.date_range(marketing["date"].min(), marketing["date"].max(), freq="D"))
        * len(channels)
    )
    missing_pairs = max(0, expected_pairs - len(marketing))
    add_result(
        results,
        "marketing_date_channel_coverage",
        "PASS" if missing_pairs == 0 else "WARN",
        f"expected_pairs={expected_pairs}, observed_pairs={len(marketing):,}, missing_pairs={missing_pairs}",
    )

    date_detail = (
        f"customers={customers['signup_date'].min().date()}..{customers['signup_date'].max().date()}, "
        f"transactions={transactions['transaction_date'].min().date()}..{transactions['transaction_date'].max().date()}, "
        f"marketing={marketing['date'].min().date()}..{marketing['date'].max().date()}"
    )
    add_result(results, "date_coverage_observed", "PASS", date_detail)

    return pd.DataFrame(results)


def write_outputs(summary: pd.DataFrame) -> None:
    OUT_TABLES_DIR.mkdir(parents=True, exist_ok=True)

    summary_path = OUT_TABLES_DIR / "raw_validation_summary.csv"
    summary.to_csv(summary_path, index=False)


def run() -> None:
    tables = load_raw_tables()
    summary = build_results(tables)
    write_outputs(summary)

    print("Raw data validation completed.")
    print(f"summary_csv: {OUT_TABLES_DIR / 'raw_validation_summary.csv'}")


def main() -> None:
    run()


if __name__ == "__main__":
    main()
