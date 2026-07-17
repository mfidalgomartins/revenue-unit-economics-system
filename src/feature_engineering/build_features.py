"""Build analytical feature tables for unit economics workflows.

Output tables:
- data/processed/customer_metrics.csv
- data/processed/cohort_table.csv
- data/processed/unit_economics.csv
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.governance.metric_registry import PAYBACK_HORIZON_MONTHS
from src.paths import PROJECT_ROOT, RAW_DATA_DIR

RAW_DIR = RAW_DATA_DIR
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    customers = pd.read_csv(RAW_DIR / "customers.csv", parse_dates=["signup_date"])
    transactions = pd.read_csv(RAW_DIR / "transactions.csv", parse_dates=["transaction_date"])
    marketing_spend = pd.read_csv(RAW_DIR / "marketing_spend.csv", parse_dates=["date"])
    return customers, transactions, marketing_spend


def build_customer_metrics(customers: pd.DataFrame, transactions: pd.DataFrame) -> pd.DataFrame:
    tx_agg = transactions.groupby("customer_id", as_index=False).agg(
        first_transaction_date=("transaction_date", "min"),
        last_transaction_date=("transaction_date", "max"),
        total_revenue=("revenue", "sum"),
        total_cost=("cost", "sum"),
        transaction_count=("transaction_id", "count"),
    )

    customer_metrics = customers.merge(tx_agg, on="customer_id", how="left")

    customer_metrics["total_revenue"] = customer_metrics["total_revenue"].fillna(0.0)
    customer_metrics["total_cost"] = customer_metrics["total_cost"].fillna(0.0)
    customer_metrics["transaction_count"] = (
        customer_metrics["transaction_count"].fillna(0).astype(int)
    )

    transaction_span_days = (
        customer_metrics["last_transaction_date"] - customer_metrics["first_transaction_date"]
    ).dt.days + 1
    customer_metrics["transaction_span_days"] = np.where(
        customer_metrics["transaction_count"] > 0,
        transaction_span_days,
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
    customer_metrics["revenue_per_transaction_span_day"] = np.where(
        customer_metrics["transaction_span_days"] > 0,
        customer_metrics["total_revenue"] / customer_metrics["transaction_span_days"],
        0.0,
    )

    ordered_cols = [
        "customer_id",
        "segment",
        "region",
        "acquisition_channel",
        "first_transaction_date",
        "last_transaction_date",
        "transaction_span_days",
        "total_revenue",
        "total_cost",
        "contribution_margin",
        "contribution_margin_pct",
        "transaction_count",
        "avg_revenue_per_transaction",
        "revenue_per_transaction_span_day",
    ]

    customer_metrics = customer_metrics[ordered_cols].sort_values(
        ["acquisition_channel", "customer_id"], ignore_index=True
    )

    money_cols = [
        "total_revenue",
        "total_cost",
        "contribution_margin",
        "avg_revenue_per_transaction",
        "revenue_per_transaction_span_day",
    ]
    customer_metrics[money_cols] = customer_metrics[money_cols].round(2)
    customer_metrics["contribution_margin_pct"] = customer_metrics["contribution_margin_pct"].round(
        6
    )

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

    customer_activity = tx_customer[
        ["cohort_month", "activity_month", "customer_id"]
    ].drop_duplicates()
    month_0_members = customer_activity.loc[
        customer_activity["cohort_month"] == customer_activity["activity_month"],
        ["cohort_month", "customer_id"],
    ].drop_duplicates()

    retained_activity = customer_activity.merge(
        month_0_members,
        on=["cohort_month", "customer_id"],
        how="inner",
        validate="many_to_one",
    )
    retained_counts = retained_activity.groupby(
        ["cohort_month", "activity_month"], as_index=False
    ).agg(retained_month_0_customers=("customer_id", "nunique"))

    observed = (
        tx_customer.groupby(["cohort_month", "activity_month"], as_index=False)
        .agg(
            customers_active=("customer_id", "nunique"),
            cohort_revenue=("revenue", "sum"),
        )
        .merge(
            retained_counts,
            on=["cohort_month", "activity_month"],
            how="left",
            validate="one_to_one",
        )
    )
    observed["retained_month_0_customers"] = (
        observed["retained_month_0_customers"].fillna(0).astype(int)
    )

    customer_cohorts = customers.assign(
        cohort_month=customers["signup_date"].dt.to_period("M").dt.to_timestamp()
    )
    cohort_sizes = customer_cohorts.groupby("cohort_month", as_index=False).agg(
        cohort_size=("customer_id", "nunique")
    )
    month_0_counts = month_0_members.groupby("cohort_month", as_index=False).agg(
        month_0_active_customers=("customer_id", "nunique")
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
        .merge(cohort_sizes, on="cohort_month", how="left", validate="many_to_one")
        .merge(month_0_counts, on="cohort_month", how="left", validate="many_to_one")
    )
    cohort_table["customers_active"] = cohort_table["customers_active"].astype(int)
    cohort_table["retained_month_0_customers"] = cohort_table["retained_month_0_customers"].astype(
        int
    )
    cohort_table["cohort_size"] = cohort_table["cohort_size"].astype(int)
    cohort_table["month_0_active_customers"] = (
        cohort_table["month_0_active_customers"].fillna(0).astype(int)
    )
    cohort_table["late_activation_customers"] = (
        cohort_table["customers_active"] - cohort_table["retained_month_0_customers"]
    )

    cohort_table["month_0_activation_rate"] = np.where(
        cohort_table["cohort_size"] > 0,
        cohort_table["month_0_active_customers"] / cohort_table["cohort_size"],
        np.nan,
    )
    cohort_table["signup_activity_rate"] = np.where(
        cohort_table["cohort_size"] > 0,
        cohort_table["customers_active"] / cohort_table["cohort_size"],
        np.nan,
    )
    cohort_table["retained_from_month_0_rate"] = np.where(
        cohort_table["month_0_active_customers"] > 0,
        cohort_table["retained_month_0_customers"] / cohort_table["month_0_active_customers"],
        np.nan,
    )

    cohort_table["average_revenue_per_active_customer"] = np.where(
        cohort_table["customers_active"] > 0,
        cohort_table["cohort_revenue"] / cohort_table["customers_active"],
        0.0,
    )

    cohort_table = cohort_table[
        [
            "cohort_month",
            "activity_month",
            "cohort_size",
            "customers_active",
            "month_0_active_customers",
            "retained_month_0_customers",
            "late_activation_customers",
            "month_0_activation_rate",
            "signup_activity_rate",
            "retained_from_month_0_rate",
            "cohort_revenue",
            "average_revenue_per_active_customer",
        ]
    ].sort_values(["cohort_month", "activity_month"], ignore_index=True)

    cohort_table["cohort_revenue"] = cohort_table["cohort_revenue"].round(2)
    cohort_table["average_revenue_per_active_customer"] = cohort_table[
        "average_revenue_per_active_customer"
    ].round(2)
    rate_cols = [
        "month_0_activation_rate",
        "signup_activity_rate",
        "retained_from_month_0_rate",
    ]
    cohort_table[rate_cols] = cohort_table[rate_cols].round(6)
    return cohort_table


def _build_payback_metrics(
    customers: pd.DataFrame,
    transactions: pd.DataFrame,
    marketing_spend: pd.DataFrame,
    unit_economics: pd.DataFrame,
    observation_end: pd.Timestamp,
    horizon_months: int = PAYBACK_HORIZON_MONTHS,
) -> pd.DataFrame:
    """Calculate empirical payback from mature acquisition-cohort contribution curves."""
    customer_cohorts = customers[["customer_id", "signup_date", "acquisition_channel"]].copy()
    customer_cohorts["cohort_month"] = (
        customer_cohorts["signup_date"].dt.to_period("M").dt.to_timestamp()
    )
    observation_month = observation_end.to_period("M").to_timestamp()
    customer_cohorts["observable_age_months"] = (
        (observation_month.year - customer_cohorts["cohort_month"].dt.year) * 12
        + observation_month.month
        - customer_cohorts["cohort_month"].dt.month
    )
    mature_customers = customer_cohorts.loc[
        customer_cohorts["observable_age_months"] >= horizon_months
    ].copy()

    mature_counts = mature_customers.groupby("acquisition_channel", as_index=False).agg(
        payback_mature_customers=("customer_id", "nunique")
    )
    acquisition_windows = mature_customers.groupby("acquisition_channel", as_index=False).agg(
        payback_acquisition_start=("signup_date", "min"),
        payback_acquisition_end=("signup_date", "max"),
    )
    aligned_spend = marketing_spend.merge(
        acquisition_windows,
        on="acquisition_channel",
        how="inner",
        validate="many_to_one",
    )
    aligned_spend = aligned_spend.loc[
        aligned_spend["date"].between(
            aligned_spend["payback_acquisition_start"],
            aligned_spend["payback_acquisition_end"],
        )
    ]
    aligned_spend = aligned_spend.groupby("acquisition_channel", as_index=False).agg(
        payback_aligned_spend=("spend", "sum")
    )
    payback_cac = acquisition_windows.merge(
        mature_counts,
        on="acquisition_channel",
        how="left",
        validate="one_to_one",
    ).merge(
        aligned_spend,
        on="acquisition_channel",
        how="left",
        validate="one_to_one",
    )
    payback_cac["payback_cac"] = np.where(
        payback_cac["payback_mature_customers"] > 0,
        payback_cac["payback_aligned_spend"] / payback_cac["payback_mature_customers"],
        np.nan,
    )

    if transactions.empty or mature_customers.empty:
        monthly_contribution = pd.DataFrame(
            columns=["acquisition_channel", "age_month", "contribution_margin"]
        )
    else:
        mature_transactions = transactions.merge(
            mature_customers[["customer_id", "acquisition_channel", "cohort_month"]],
            on="customer_id",
            how="inner",
            validate="many_to_one",
        )
        transaction_month = (
            mature_transactions["transaction_date"].dt.to_period("M").dt.to_timestamp()
        )
        mature_transactions["age_month"] = (
            (transaction_month.dt.year - mature_transactions["cohort_month"].dt.year) * 12
            + transaction_month.dt.month
            - mature_transactions["cohort_month"].dt.month
        )
        mature_transactions = mature_transactions.loc[
            mature_transactions["age_month"].between(0, horizon_months)
        ].copy()
        mature_transactions["contribution_margin"] = (
            mature_transactions["revenue"] - mature_transactions["cost"]
        )
        monthly_contribution = mature_transactions.groupby(
            ["acquisition_channel", "age_month"], as_index=False
        ).agg(contribution_margin=("contribution_margin", "sum"))

    channels = unit_economics["acquisition_channel"].tolist()
    complete_index = pd.MultiIndex.from_product(
        [channels, range(horizon_months + 1)],
        names=["acquisition_channel", "age_month"],
    )
    curve = (
        monthly_contribution.set_index(["acquisition_channel", "age_month"])
        .reindex(complete_index, fill_value=0.0)
        .reset_index()
        .merge(mature_counts, on="acquisition_channel", how="left", validate="many_to_one")
        .merge(
            payback_cac[["acquisition_channel", "payback_cac"]],
            on="acquisition_channel",
            how="left",
            validate="many_to_one",
        )
    )
    curve["payback_mature_customers"] = curve["payback_mature_customers"].fillna(0).astype(int)
    curve["contribution_margin"] = pd.to_numeric(
        curve["contribution_margin"], errors="coerce"
    ).fillna(0.0)
    curve["cumulative_contribution"] = curve.groupby("acquisition_channel", sort=False)[
        "contribution_margin"
    ].cumsum()
    curve["cumulative_contribution_per_customer"] = np.where(
        curve["payback_mature_customers"] > 0,
        curve["cumulative_contribution"] / curve["payback_mature_customers"],
        np.nan,
    )

    recovered = curve.loc[
        (curve["payback_mature_customers"] > 0)
        & (curve["payback_cac"] >= 0)
        & (curve["cumulative_contribution_per_customer"] >= curve["payback_cac"])
    ]
    first_recovery = recovered.groupby("acquisition_channel", as_index=False).agg(
        approximate_payback_period=("age_month", "min")
    )
    horizon_contribution = curve.loc[
        curve["age_month"] == horizon_months,
        [
            "acquisition_channel",
            "cumulative_contribution_per_customer",
        ],
    ].rename(
        columns={
            "cumulative_contribution_per_customer": ("payback_horizon_contribution_per_customer")
        }
    )

    payback = (
        unit_economics[["acquisition_channel", "customers_acquired"]]
        .merge(payback_cac, on="acquisition_channel", how="left")
        .merge(first_recovery, on="acquisition_channel", how="left")
        .merge(horizon_contribution, on="acquisition_channel", how="left")
    )
    payback["payback_mature_customers"] = payback["payback_mature_customers"].fillna(0).astype(int)
    payback["payback_horizon_months"] = horizon_months
    payback["payback_mature_customer_share"] = np.where(
        payback["customers_acquired"] > 0,
        payback["payback_mature_customers"] / payback["customers_acquired"],
        np.nan,
    )
    payback["payback_status"] = np.select(
        [
            payback["payback_mature_customers"] == 0,
            payback["payback_cac"].isna(),
            payback["approximate_payback_period"].notna(),
        ],
        ["insufficient_maturity", "insufficient_spend_alignment", "recovered"],
        default="not_recovered",
    )
    payback["payback_is_censored"] = payback["payback_status"].eq("not_recovered")
    return payback.drop(columns="customers_acquired")


def build_unit_economics(
    customers: pd.DataFrame,
    marketing_spend: pd.DataFrame,
    customer_metrics: pd.DataFrame,
    transactions: pd.DataFrame,
) -> pd.DataFrame:
    customers_by_channel = customers.groupby("acquisition_channel", as_index=False).agg(
        customers_acquired=("customer_id", "nunique")
    )
    spend_by_channel = marketing_spend.groupby("acquisition_channel", as_index=False).agg(
        total_spend=("spend", "sum")
    )

    # LTV assumption: observed lifetime contribution margin per acquired customer.
    ltv_by_channel = customer_metrics.groupby("acquisition_channel", as_index=False).agg(
        average_LTV=("contribution_margin", "mean"),
        median_LTV=("contribution_margin", "median"),
        total_channel_contribution_margin=("contribution_margin", "sum"),
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

    observation_candidates = [
        customers["signup_date"].max(),
        marketing_spend["date"].max(),
    ]
    if not transactions.empty:
        observation_candidates.append(transactions["transaction_date"].max())
    observation_end = max(
        pd.Timestamp(value) for value in observation_candidates if pd.notna(value)
    )
    payback_metrics = _build_payback_metrics(
        customers,
        transactions,
        marketing_spend,
        unit_economics,
        observation_end,
    )
    unit_economics = unit_economics.merge(
        payback_metrics,
        on="acquisition_channel",
        how="left",
        validate="one_to_one",
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
            "payback_cac",
            "payback_aligned_spend",
            "payback_acquisition_start",
            "payback_acquisition_end",
            "approximate_payback_period",
            "payback_status",
            "payback_is_censored",
            "payback_horizon_months",
            "payback_mature_customers",
            "payback_mature_customer_share",
            "payback_horizon_contribution_per_customer",
        ]
    ].sort_values("acquisition_channel", ignore_index=True)

    round_cols = [
        "total_spend",
        "CAC",
        "average_LTV",
        "median_LTV",
        "total_channel_contribution_margin",
        "LTV_to_CAC",
        "payback_cac",
        "payback_aligned_spend",
        "approximate_payback_period",
        "payback_mature_customer_share",
        "payback_horizon_contribution_per_customer",
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
    cohort_table_out["activity_month"] = pd.to_datetime(cohort_table_out["activity_month"]).dt.date
    for column in ("payback_acquisition_start", "payback_acquisition_end"):
        unit_economics_out[column] = pd.to_datetime(unit_economics_out[column]).dt.date

    customer_metrics_out.to_csv(PROCESSED_DIR / "customer_metrics.csv", index=False)
    cohort_table_out.to_csv(PROCESSED_DIR / "cohort_table.csv", index=False)
    unit_economics_out.to_csv(PROCESSED_DIR / "unit_economics.csv", index=False)


def run() -> None:
    customers, transactions, marketing_spend = load_inputs()
    customer_metrics = build_customer_metrics(customers, transactions)
    cohort_table = build_cohort_table(customers, transactions)
    unit_economics = build_unit_economics(
        customers,
        marketing_spend,
        customer_metrics,
        transactions,
    )

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
