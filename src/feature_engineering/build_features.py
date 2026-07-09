"""Build analytical feature tables for unit economics workflows.

Output tables:
- data/processed/customer_metrics.csv
- data/processed/cohort_table.csv
- data/processed/unit_economics.csv
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.paths import PROJECT_ROOT

RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    customers = pd.read_csv(RAW_DIR / "customers.csv", parse_dates=["signup_date"])
    transactions = pd.read_csv(RAW_DIR / "transactions.csv", parse_dates=["transaction_date"])
    marketing_spend = pd.read_csv(RAW_DIR / "marketing_spend.csv", parse_dates=["date"])
    return customers, transactions, marketing_spend


def build_customer_metrics(customers: pd.DataFrame, transactions: pd.DataFrame) -> pd.DataFrame:
    tx_agg = (
        transactions.groupby("customer_id", as_index=False)
        .agg(
            first_transaction_date=("transaction_date", "min"),
            last_transaction_date=("transaction_date", "max"),
            total_revenue=("revenue", "sum"),
            total_cost=("cost", "sum"),
            transaction_count=("transaction_id", "count"),
        )
    )

    customer_metrics = customers.merge(tx_agg, on="customer_id", how="left")

    customer_metrics["total_revenue"] = customer_metrics["total_revenue"].fillna(0.0)
    customer_metrics["total_cost"] = customer_metrics["total_cost"].fillna(0.0)
    customer_metrics["transaction_count"] = (
        customer_metrics["transaction_count"].fillna(0).astype(int)
    )

    tx_lifetime_days = (
        customer_metrics["last_transaction_date"] - customer_metrics["first_transaction_date"]
    ).dt.days + 1
    customer_metrics["lifetime_days"] = np.where(
        customer_metrics["transaction_count"] > 0,
        tx_lifetime_days,
        0,
    ).astype(int)

    customer_metrics["contribution_margin"] = (
        customer_metrics["total_revenue"] - customer_metrics["total_cost"]
    )

    # Keep percentage and rate features at 0 when denominator is 0 for interpretability in downstream tables.
    customer_metrics["contribution_margin_pct"] = np.where(
        customer_metrics["total_revenue"] > 0,
        customer_metrics["contribution_margin"] / customer_metrics["total_revenue"],
        0.0,
    )
    customer_metrics["avg_revenue_per_transaction"] = np.where(
        customer_metrics["transaction_count"] > 0,
        customer_metrics["total_revenue"] / customer_metrics["transaction_count"],
        0.0,
    )
    customer_metrics["revenue_per_day"] = np.where(
        customer_metrics["lifetime_days"] > 0,
        customer_metrics["total_revenue"] / customer_metrics["lifetime_days"],
        0.0,
    )

    ordered_cols = [
        "customer_id",
        "segment",
        "region",
        "acquisition_channel",
        "first_transaction_date",
        "last_transaction_date",
        "lifetime_days",
        "total_revenue",
        "total_cost",
        "contribution_margin",
        "contribution_margin_pct",
        "transaction_count",
        "avg_revenue_per_transaction",
        "revenue_per_day",
    ]

    customer_metrics = customer_metrics[ordered_cols].sort_values(
        ["acquisition_channel", "customer_id"], ignore_index=True
    )

    money_cols = [
        "total_revenue",
        "total_cost",
        "contribution_margin",
        "avg_revenue_per_transaction",
        "revenue_per_day",
    ]
    customer_metrics[money_cols] = customer_metrics[money_cols].round(2)
    customer_metrics["contribution_margin_pct"] = customer_metrics[
        "contribution_margin_pct"
    ].round(6)

    return customer_metrics


def build_cohort_table(customers: pd.DataFrame, transactions: pd.DataFrame) -> pd.DataFrame:
    observation_end = max(customers["signup_date"].max(), transactions["transaction_date"].max())

    tx_customer = transactions.merge(
        customers[["customer_id", "signup_date"]],
        on="customer_id",
        how="left",
        validate="many_to_one",
    )

    tx_customer["cohort_month"] = tx_customer["signup_date"].dt.to_period("M").dt.to_timestamp()
    tx_customer["activity_month"] = (
        tx_customer["transaction_date"].dt.to_period("M").dt.to_timestamp()
    )

    observed = (
        tx_customer.groupby(["cohort_month", "activity_month"], as_index=False)
        .agg(
            customers_active=("customer_id", "nunique"),
            cohort_revenue=("revenue", "sum"),
        )
    )

    cohort_months = (
        customers["signup_date"].dt.to_period("M").dt.to_timestamp().drop_duplicates().sort_values()
    )
    activity_months = pd.date_range(cohort_months.min(), observation_end, freq="MS")
    complete_index = pd.MultiIndex.from_product(
        [cohort_months, activity_months],
        names=["cohort_month", "activity_month"],
    )
    complete_index = complete_index[
        complete_index.get_level_values("activity_month")
        >= complete_index.get_level_values("cohort_month")
    ]

    cohort_table = (
        observed.set_index(["cohort_month", "activity_month"])
        .reindex(complete_index, fill_value=0)
        .reset_index()
    )
    cohort_table["customers_active"] = cohort_table["customers_active"].astype(int)

    cohort_table["average_revenue_per_active_customer"] = np.where(
        cohort_table["customers_active"] > 0,
        cohort_table["cohort_revenue"] / cohort_table["customers_active"],
        0.0,
    )

    cohort_table = cohort_table[
        [
            "cohort_month",
            "activity_month",
            "customers_active",
            "cohort_revenue",
            "average_revenue_per_active_customer",
        ]
    ].sort_values(["cohort_month", "activity_month"], ignore_index=True)

    cohort_table["cohort_revenue"] = cohort_table["cohort_revenue"].round(2)
    cohort_table["average_revenue_per_active_customer"] = cohort_table[
        "average_revenue_per_active_customer"
    ].round(2)
    return cohort_table


def build_unit_economics(
    customers: pd.DataFrame,
    marketing_spend: pd.DataFrame,
    customer_metrics: pd.DataFrame,
) -> pd.DataFrame:
    customers_by_channel = (
        customers.groupby("acquisition_channel", as_index=False)
        .agg(customers_acquired=("customer_id", "nunique"))
    )
    spend_by_channel = (
        marketing_spend.groupby("acquisition_channel", as_index=False)
        .agg(total_spend=("spend", "sum"))
    )

    # LTV assumption: observed lifetime contribution margin per acquired customer.
    ltv_by_channel = (
        customer_metrics.groupby("acquisition_channel", as_index=False)
        .agg(
            average_LTV=("contribution_margin", "mean"),
            median_LTV=("contribution_margin", "median"),
            total_channel_contribution_margin=("contribution_margin", "sum"),
        )
    )

    unit_economics = (
        customers_by_channel.merge(spend_by_channel, on="acquisition_channel", how="left")
        .merge(ltv_by_channel, on="acquisition_channel", how="left")
        .fillna(
            {
                "total_spend": 0.0,
                "average_LTV": 0.0,
                "median_LTV": 0.0,
                "total_channel_contribution_margin": 0.0,
            }
        )
    )

    unit_economics["CAC"] = np.where(
        unit_economics["customers_acquired"] > 0,
        unit_economics["total_spend"] / unit_economics["customers_acquired"],
        np.nan,
    )
    unit_economics["LTV_to_CAC"] = np.where(
        unit_economics["CAC"] > 0,
        unit_economics["average_LTV"] / unit_economics["CAC"],
        np.nan,
    )

    observed_months = marketing_spend["date"].dt.to_period("M").nunique()
    avg_monthly_cm_per_customer = np.where(
        unit_economics["customers_acquired"] > 0,
        (unit_economics["total_channel_contribution_margin"] / observed_months)
        / unit_economics["customers_acquired"],
        np.nan,
    )

    # Payback assumption: CAC divided by average monthly contribution margin per acquired customer.
    # If average monthly CM is <= 0, payback is undefined (np.nan).
    unit_economics["approximate_payback_period"] = np.where(
        avg_monthly_cm_per_customer > 0,
        unit_economics["CAC"] / avg_monthly_cm_per_customer,
        np.nan,
    )

    unit_economics = unit_economics[
        [
            "acquisition_channel",
            "customers_acquired",
            "total_spend",
            "CAC",
            "average_LTV",
            "median_LTV",
            "total_channel_contribution_margin",
            "LTV_to_CAC",
            "approximate_payback_period",
        ]
    ].sort_values("acquisition_channel", ignore_index=True)

    round_cols = [
        "total_spend",
        "CAC",
        "average_LTV",
        "median_LTV",
        "total_channel_contribution_margin",
        "LTV_to_CAC",
        "approximate_payback_period",
    ]
    unit_economics[round_cols] = unit_economics[round_cols].round(4)
    return unit_economics


def save_outputs(
    customer_metrics: pd.DataFrame,
    cohort_table: pd.DataFrame,
    unit_economics: pd.DataFrame,
) -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    customer_metrics_out = customer_metrics.copy()
    cohort_table_out = cohort_table.copy()
    unit_economics_out = unit_economics.copy()

    customer_metrics_out["first_transaction_date"] = pd.to_datetime(
        customer_metrics_out["first_transaction_date"]
    ).dt.date
    customer_metrics_out["last_transaction_date"] = pd.to_datetime(
        customer_metrics_out["last_transaction_date"]
    ).dt.date
    cohort_table_out["cohort_month"] = pd.to_datetime(cohort_table_out["cohort_month"]).dt.date
    cohort_table_out["activity_month"] = pd.to_datetime(
        cohort_table_out["activity_month"]
    ).dt.date

    customer_metrics_out.to_csv(PROCESSED_DIR / "customer_metrics.csv", index=False)
    cohort_table_out.to_csv(PROCESSED_DIR / "cohort_table.csv", index=False)
    unit_economics_out.to_csv(PROCESSED_DIR / "unit_economics.csv", index=False)


def run() -> None:
    customers, transactions, marketing_spend = load_inputs()
    customer_metrics = build_customer_metrics(customers, transactions)
    cohort_table = build_cohort_table(customers, transactions)
    unit_economics = build_unit_economics(customers, marketing_spend, customer_metrics)

    save_outputs(customer_metrics, cohort_table, unit_economics)

    print("Feature engineering completed.")
    print(f"customer_metrics rows: {len(customer_metrics):,}")
    print(f"cohort_table rows: {len(cohort_table):,}")
    print(f"unit_economics rows: {len(unit_economics):,}")
    print(f"output_dir: {PROCESSED_DIR}")


def main() -> None:
    run()


if __name__ == "__main__":
    main()
