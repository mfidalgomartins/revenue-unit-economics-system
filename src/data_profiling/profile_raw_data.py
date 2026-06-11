"""Profile raw datasets and produce a formal data quality review."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
OUTPUT_TABLES_DIR = PROJECT_ROOT / "outputs" / "tables"


@dataclass(frozen=True)
class TableSpec:
    name: str
    file_name: str
    grain: str
    candidate_keys: list[list[str]]
    date_columns: list[str]
    categorical_columns: list[str]
    likely_dimensions: list[str]
    likely_metrics: list[str]


TABLE_SPECS = [
    TableSpec(
        name="customers",
        file_name="customers.csv",
        grain="One row per customer_id",
        candidate_keys=[["customer_id"]],
        date_columns=["signup_date"],
        categorical_columns=["segment", "region", "acquisition_channel"],
        likely_dimensions=["segment", "region", "acquisition_channel", "signup_date"],
        likely_metrics=["customer_count"],
    ),
    TableSpec(
        name="transactions",
        file_name="transactions.csv",
        grain="One row per transaction_id",
        candidate_keys=[["transaction_id"]],
        date_columns=["transaction_date"],
        categorical_columns=["product_type", "customer_id"],
        likely_dimensions=["transaction_date", "product_type", "customer_id"],
        likely_metrics=["revenue", "cost", "contribution_margin", "transaction_count"],
    ),
    TableSpec(
        name="marketing_spend",
        file_name="marketing_spend.csv",
        grain="One row per date x acquisition_channel",
        candidate_keys=[["date", "acquisition_channel"]],
        date_columns=["date"],
        categorical_columns=["acquisition_channel"],
        likely_dimensions=["date", "acquisition_channel"],
        likely_metrics=["spend"],
    ),
]

CUSTOMER_ALLOWED_SEGMENTS = {"Startup", "SMB", "Mid-Market", "Enterprise"}
CUSTOMER_ALLOWED_REGIONS = {"North America", "EMEA", "LATAM", "APAC"}
ALLOWED_CHANNELS = {"paid_search", "social_ads", "referral", "organic", "partners", "email"}
ALLOWED_PRODUCT_TYPES = {"Core", "Add-on", "Premium", "Services"}
NEGATIVE_MARGIN_REVIEW_THRESHOLD = 0.01


def load_tables() -> dict[str, pd.DataFrame]:
    tables: dict[str, pd.DataFrame] = {}
    for spec in TABLE_SPECS:
        path = RAW_DIR / spec.file_name
        parse_dates = spec.date_columns if spec.date_columns else None
        tables[spec.name] = pd.read_csv(path, parse_dates=parse_dates)
    return tables


def detect_candidate_key(df: pd.DataFrame, candidate_keys: list[list[str]]) -> tuple[str, int]:
    for key_columns in candidate_keys:
        key_nulls = int(df[key_columns].isna().any(axis=1).sum())
        duplicate_key_rows = int(df.duplicated(subset=key_columns).sum())
        if key_nulls == 0 and duplicate_key_rows == 0:
            return ", ".join(key_columns), duplicate_key_rows
    fallback = ", ".join(candidate_keys[0]) if candidate_keys else "None"
    fallback_dupes = int(df.duplicated(subset=candidate_keys[0]).sum()) if candidate_keys else int(df.duplicated().sum())
    return f"{fallback} (not unique)", fallback_dupes




def make_issue(
    table_name: str,
    column_name: str,
    check_name: str,
    severity: str,
    issue_count: int,
    row_count: int,
    description: str,
) -> dict:
    issue_rate = (issue_count / row_count) if row_count else 0.0
    return {
        "table_name": table_name,
        "column_name": column_name,
        "check_name": check_name,
        "severity": severity,
        "issue_count": int(issue_count),
        "issue_rate": issue_rate,
        "description": description,
    }


def evaluate_data_quality(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    customers = tables["customers"].copy()
    transactions = tables["transactions"].copy()
    marketing = tables["marketing_spend"].copy()

    issues: list[dict] = []

    customers_rows = len(customers)
    transactions_rows = len(transactions)
    marketing_rows = len(marketing)

    # Customers checks.
    issues.append(
        make_issue(
            "customers",
            "customer_id",
            "duplicate_customer_id",
            "high",
            int(customers.duplicated(subset=["customer_id"]).sum()),
            customers_rows,
            "customer_id should be unique at customer grain.",
        )
    )
    invalid_segments = int((~customers["segment"].isin(CUSTOMER_ALLOWED_SEGMENTS)).sum())
    issues.append(
        make_issue(
            "customers",
            "segment",
            "invalid_segment_value",
            "medium",
            invalid_segments,
            customers_rows,
            "segment contains unexpected categories.",
        )
    )
    invalid_regions = int((~customers["region"].isin(CUSTOMER_ALLOWED_REGIONS)).sum())
    issues.append(
        make_issue(
            "customers",
            "region",
            "invalid_region_value",
            "medium",
            invalid_regions,
            customers_rows,
            "region contains unexpected categories.",
        )
    )
    invalid_customer_channels = int((~customers["acquisition_channel"].isin(ALLOWED_CHANNELS)).sum())
    issues.append(
        make_issue(
            "customers",
            "acquisition_channel",
            "invalid_channel_value",
            "medium",
            invalid_customer_channels,
            customers_rows,
            "acquisition_channel contains unexpected categories.",
        )
    )

    # Transactions checks.
    issues.append(
        make_issue(
            "transactions",
            "transaction_id",
            "duplicate_transaction_id",
            "high",
            int(transactions.duplicated(subset=["transaction_id"]).sum()),
            transactions_rows,
            "transaction_id should be unique at transaction grain.",
        )
    )
    invalid_customer_fk = int((~transactions["customer_id"].isin(customers["customer_id"])).sum())
    issues.append(
        make_issue(
            "transactions",
            "customer_id",
            "orphan_customer_id",
            "high",
            invalid_customer_fk,
            transactions_rows,
            "transactions.customer_id must exist in customers.customer_id.",
        )
    )
    invalid_product_types = int((~transactions["product_type"].isin(ALLOWED_PRODUCT_TYPES)).sum())
    issues.append(
        make_issue(
            "transactions",
            "product_type",
            "invalid_product_type",
            "medium",
            invalid_product_types,
            transactions_rows,
            "product_type contains unexpected categories.",
        )
    )
    non_positive_revenue = int((transactions["revenue"] <= 0).sum())
    issues.append(
        make_issue(
            "transactions",
            "revenue",
            "non_positive_revenue",
            "high",
            non_positive_revenue,
            transactions_rows,
            "revenue should be strictly positive.",
        )
    )
    negative_cost = int((transactions["cost"] < 0).sum())
    issues.append(
        make_issue(
            "transactions",
            "cost",
            "negative_cost",
            "high",
            negative_cost,
            transactions_rows,
            "cost should not be negative.",
        )
    )
    cost_above_revenue = int((transactions["cost"] > transactions["revenue"]).sum())
    cost_above_revenue_rate = cost_above_revenue / transactions_rows
    issues.append(
        make_issue(
            "transactions",
            "cost",
            "cost_exceeds_revenue",
            "medium" if cost_above_revenue_rate > NEGATIVE_MARGIN_REVIEW_THRESHOLD else "low",
            cost_above_revenue,
            transactions_rows,
            "cost > revenue creates negative contribution margin and should be monitored.",
        )
    )

    joined = transactions.merge(customers[["customer_id", "signup_date"]], on="customer_id", how="left")
    tx_before_signup = int((joined["transaction_date"] < joined["signup_date"]).sum())
    issues.append(
        make_issue(
            "transactions",
            "transaction_date",
            "transaction_before_signup",
            "high",
            tx_before_signup,
            transactions_rows,
            "transaction_date should not be earlier than the customer's signup_date.",
        )
    )

    # Marketing checks.
    issues.append(
        make_issue(
            "marketing_spend",
            "date, acquisition_channel",
            "duplicate_marketing_grain",
            "high",
            int(marketing.duplicated(subset=["date", "acquisition_channel"]).sum()),
            marketing_rows,
            "date + acquisition_channel should define a unique row.",
        )
    )
    invalid_marketing_channels = int((~marketing["acquisition_channel"].isin(ALLOWED_CHANNELS)).sum())
    issues.append(
        make_issue(
            "marketing_spend",
            "acquisition_channel",
            "invalid_channel_value",
            "medium",
            invalid_marketing_channels,
            marketing_rows,
            "acquisition_channel contains unexpected categories.",
        )
    )
    negative_spend = int((marketing["spend"] < 0).sum())
    issues.append(
        make_issue(
            "marketing_spend",
            "spend",
            "negative_spend",
            "high",
            negative_spend,
            marketing_rows,
            "marketing spend should not be negative.",
        )
    )
    zero_spend = int((marketing["spend"] == 0).sum())
    issues.append(
        make_issue(
            "marketing_spend",
            "spend",
            "zero_spend",
            "low",
            zero_spend,
            marketing_rows,
            "zero spend rows can be valid but should be reviewed for campaign inactivity.",
        )
    )

    expected_dates = pd.date_range(marketing["date"].min(), marketing["date"].max(), freq="D")
    expected_pairs = len(expected_dates) * len(ALLOWED_CHANNELS)
    missing_pairs = max(0, expected_pairs - len(marketing))
    issues.append(
        make_issue(
            "marketing_spend",
            "date, acquisition_channel",
            "missing_date_channel_pairs",
            "medium",
            missing_pairs,
            expected_pairs,
            "missing date-channel combinations can break CAC and time-series analysis.",
        )
    )

    issues_df = pd.DataFrame(issues)
    return issues_df.loc[issues_df["issue_count"] > 0].reset_index(drop=True)


def summarize_tables(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for spec in TABLE_SPECS:
        df = tables[spec.name]
        candidate_pk, duplicate_pk_rows = detect_candidate_key(df, spec.candidate_keys)
        duplicate_rows = int(df.duplicated().sum())
        date_min = ""
        date_max = ""
        if spec.date_columns:
            date_col = spec.date_columns[0]
            date_min = str(df[date_col].min().date()) if pd.notna(df[date_col].min()) else ""
            date_max = str(df[date_col].max().date()) if pd.notna(df[date_col].max()) else ""

        rows.append(
            {
                "table_name": spec.name,
                "grain": spec.grain,
                "row_count": len(df),
                "column_count": len(df.columns),
                "candidate_primary_key": candidate_pk,
                "duplicate_rows": duplicate_rows,
                "duplicate_candidate_key_rows": duplicate_pk_rows,
                "date_min": date_min,
                "date_max": date_max,
                "likely_useful_dimensions": ", ".join(spec.likely_dimensions),
                "likely_useful_metrics": ", ".join(spec.likely_metrics),
            }
        )
    return pd.DataFrame(rows)


def run() -> None:
    OUTPUT_TABLES_DIR.mkdir(parents=True, exist_ok=True)

    tables = load_tables()
    summary_df = summarize_tables(tables)
    issues_df = evaluate_data_quality(tables)

    summary_df.to_csv(OUTPUT_TABLES_DIR / "data_profile_summary.csv", index=False)
    issues_df.to_csv(OUTPUT_TABLES_DIR / "data_quality_issues.csv", index=False)

    print("Profiling and data quality review completed.")
    print(f"summary_table: {OUTPUT_TABLES_DIR / 'data_profile_summary.csv'}")
    print(f"quality_issues: {OUTPUT_TABLES_DIR / 'data_quality_issues.csv'}")


def main() -> None:
    run()


if __name__ == "__main__":
    main()
