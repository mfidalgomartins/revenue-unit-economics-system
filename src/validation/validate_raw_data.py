"""Validate raw source contracts and stop the pipeline on blocking failures."""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

from src.data_contracts import (
    RAW_ALLOWED_VALUES,
    RAW_DATE_COLUMNS,
    RAW_NONNEGATIVE_COLUMNS,
    RAW_NUMERIC_COLUMNS,
    RAW_SCHEMAS,
)
from src.ingestion.contracts import ContractViolation
from src.ingestion.publish import verify_bundle
from src.paths import PROJECT_ROOT, RAW_DATA_DIR

RAW_DIR = RAW_DATA_DIR
OUT_TABLES_DIR = PROJECT_ROOT / "outputs" / "tables"
NEGATIVE_MARGIN_REVIEW_THRESHOLD = 0.01


class RawDataValidationError(RuntimeError):
    """Raised after the validation report is written and blocking checks fail."""


def _verify_bundle_if_present() -> dict[str, object] | None:
    """Verify immutable publication evidence for external bundles."""
    if not (RAW_DIR / "manifest.json").is_file():
        if os.getenv("PIPELINE_PROFILE", "synthetic") == "external":
            raise ContractViolation(
                "the external pipeline profile requires a verified bundle manifest"
            )
        return None
    return verify_bundle(RAW_DIR)


def load_raw_tables() -> dict[str, pd.DataFrame]:
    """Load raw CSVs and coerce contract types so invalid values are reportable."""
    tables: dict[str, pd.DataFrame] = {}
    for table_name in RAW_SCHEMAS:
        path = RAW_DIR / f"{table_name}.csv"
        if not path.exists():
            continue
        try:
            frame = pd.read_csv(path)
        except (OSError, UnicodeError, pd.errors.ParserError) as exc:
            frame = pd.DataFrame()
            frame.attrs["load_error"] = f"{type(exc).__name__}: {exc}"
        for column in RAW_DATE_COLUMNS[table_name]:
            if column in frame:
                frame[column] = pd.to_datetime(frame[column], errors="coerce")
        for column in RAW_NUMERIC_COLUMNS[table_name]:
            if column in frame:
                frame[column] = pd.to_numeric(frame[column], errors="coerce")
        tables[table_name] = frame
    return tables


def add_result(
    rows: list[dict[str, str]],
    check_name: str,
    status: str,
    detail: str,
) -> None:
    rows.append({"check_name": check_name, "status": status, "detail": detail})


def _invalid_date_count(tables: dict[str, pd.DataFrame]) -> int:
    return sum(
        int(pd.to_datetime(tables[table_name][column], errors="coerce").isna().sum())
        for table_name, columns in RAW_DATE_COLUMNS.items()
        for column in columns
    )


def _invalid_numeric_count(tables: dict[str, pd.DataFrame]) -> int:
    invalid = 0
    for table_name, columns in RAW_NUMERIC_COLUMNS.items():
        for column in columns:
            values = pd.to_numeric(tables[table_name][column], errors="coerce")
            invalid += int((values.isna() | ~np.isfinite(values)).sum())
    return invalid


def _date_range_detail(values: pd.Series) -> str:
    dates = pd.to_datetime(values, errors="coerce").dropna()
    if dates.empty:
        return "unavailable"
    return f"{dates.min().date()}..{dates.max().date()}"


def build_results(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Return ordered contract checks without crashing on malformed inputs."""
    results: list[dict[str, str]] = []

    missing_tables = sorted(set(RAW_SCHEMAS) - set(tables))
    if missing_tables:
        add_result(
            results,
            "required_tables_present",
            "FAIL",
            f"missing_tables={missing_tables}",
        )
        return pd.DataFrame(results)

    load_errors = {
        table_name: str(frame.attrs["load_error"])
        for table_name, frame in tables.items()
        if "load_error" in frame.attrs
    }
    if load_errors:
        add_result(
            results,
            "raw_files_readable",
            "FAIL",
            "; ".join(f"{name}={detail}" for name, detail in sorted(load_errors.items())),
        )
        return pd.DataFrame(results)

    customers = tables["customers"]
    transactions = tables["transactions"]
    marketing = tables["marketing_spend"]
    touchpoints = tables["marketing_touchpoints"]
    experiments = tables["marketing_experiments"]
    pricing = tables["pricing_interventions"]

    row_counts = {name: len(tables[name]) for name in RAW_SCHEMAS}
    nonempty = all(count > 0 for count in row_counts.values())
    add_result(
        results,
        "table_row_count_non_zero",
        "PASS" if nonempty else "FAIL",
        ", ".join(f"{name}={count:,}" for name, count in row_counts.items()),
    )

    schema_ok = all(
        set(tables[name].columns) == set(expected_columns)
        for name, expected_columns in RAW_SCHEMAS.items()
    )
    schema_detail = "; ".join(f"{name}={list(tables[name].columns)}" for name in RAW_SCHEMAS)
    add_result(results, "schema_columns_match", "PASS" if schema_ok else "FAIL", schema_detail)

    # Dependent checks require complete schemas and at least one row per table.
    if not schema_ok or not nonempty:
        return pd.DataFrame(results)

    raw_nulls = sum(int(frame.isna().sum().sum()) for frame in tables.values())
    add_result(
        results,
        "null_values_raw_tables",
        "PASS" if raw_nulls == 0 else "FAIL",
        f"total_raw_nulls={raw_nulls}",
    )

    invalid_dates = _invalid_date_count(tables)
    invalid_numeric = _invalid_numeric_count(tables)
    add_result(
        results,
        "contract_types_and_finite_values",
        "PASS" if invalid_dates == 0 and invalid_numeric == 0 else "FAIL",
        f"invalid_dates={invalid_dates}, invalid_or_nonfinite_numeric_values={invalid_numeric}",
    )

    dup_customer = int(customers.duplicated(subset=["customer_id"]).sum())
    dup_transaction = int(transactions.duplicated(subset=["transaction_id"]).sum())
    dup_marketing = int(marketing.duplicated(subset=["date", "acquisition_channel"]).sum())
    dup_touchpoints = int(touchpoints.duplicated(subset=["touchpoint_id"]).sum())
    dup_experiments = int(experiments.duplicated(subset=["experiment_id", "customer_id"]).sum())
    dup_pricing = int(pricing.duplicated(subset=["intervention_id"]).sum())
    duplicate_status = (
        "PASS"
        if all(
            duplicate == 0
            for duplicate in (
                dup_customer,
                dup_transaction,
                dup_marketing,
                dup_touchpoints,
                dup_experiments,
                dup_pricing,
            )
        )
        else "FAIL"
    )
    add_result(
        results,
        "grain_key_uniqueness",
        duplicate_status,
        (
            f"duplicate customer_id={dup_customer}, duplicate transaction_id={dup_transaction}, "
            f"duplicate date+channel={dup_marketing}, duplicate touchpoint_id={dup_touchpoints}, "
            f"duplicate experiment+customer={dup_experiments}, "
            f"duplicate intervention_id={dup_pricing}"
        ),
    )

    invalid_domains: list[str] = []
    for (table_name, column), allowed_values in RAW_ALLOWED_VALUES.items():
        observed = set(tables[table_name][column].dropna().astype(str).unique())
        unexpected = sorted(observed - set(allowed_values))
        if unexpected:
            invalid_domains.append(f"{table_name}.{column}={unexpected}")
    add_result(
        results,
        "categorical_domain_values",
        "PASS" if not invalid_domains else "FAIL",
        "unexpected_values=none" if not invalid_domains else "; ".join(invalid_domains),
    )

    orphan_transactions = int((~transactions["customer_id"].isin(customers["customer_id"])).sum())
    orphan_touchpoints = int((~touchpoints["customer_id"].isin(customers["customer_id"])).sum())
    orphan_experiments = int((~experiments["customer_id"].isin(customers["customer_id"])).sum())
    add_result(
        results,
        "transaction_customer_referential_integrity",
        (
            "PASS"
            if orphan_transactions == 0 and orphan_touchpoints == 0 and orphan_experiments == 0
            else "FAIL"
        ),
        (
            f"orphan_transaction_rows={orphan_transactions}, "
            f"orphan_touchpoint_rows={orphan_touchpoints}, "
            f"orphan_experiment_rows={orphan_experiments}"
        ),
    )

    signup_lookup = customers.drop_duplicates("customer_id").set_index("customer_id")["signup_date"]
    transaction_dates = pd.to_datetime(transactions["transaction_date"], errors="coerce")
    signup_dates = pd.to_datetime(transactions["customer_id"].map(signup_lookup), errors="coerce")
    tx_before_signup = int((transaction_dates < signup_dates).sum())
    add_result(
        results,
        "transaction_date_not_before_signup",
        "PASS" if tx_before_signup == 0 else "FAIL",
        f"rows_with_transaction_before_signup={tx_before_signup}",
    )

    touch_dates = pd.to_datetime(touchpoints["touchpoint_date"], errors="coerce")
    touch_signup_dates = pd.to_datetime(
        touchpoints["customer_id"].map(signup_lookup), errors="coerce"
    )
    post_signup_touchpoints = int((touch_dates > touch_signup_dates).sum())
    conversion_touch_flag = touchpoints["is_conversion_touch"].astype(str).str.lower().eq("true")
    conversion_touch_counts = conversion_touch_flag.groupby(touchpoints["customer_id"]).sum()
    invalid_conversion_touch_customers = int((conversion_touch_counts != 1).sum())
    max_order = touchpoints.groupby("customer_id")["touchpoint_order"].transform("max")
    conversion_not_last = int(
        (conversion_touch_flag & (touchpoints["touchpoint_order"] != max_order)).sum()
    )
    journey_ok = (
        post_signup_touchpoints == 0
        and invalid_conversion_touch_customers == 0
        and conversion_not_last == 0
    )
    add_result(
        results,
        "marketing_journey_integrity",
        "PASS" if journey_ok else "FAIL",
        (
            f"post_signup_touchpoints={post_signup_touchpoints}, "
            f"customers_without_exactly_one_conversion_touch={invalid_conversion_touch_customers}, "
            f"conversion_touch_not_last={conversion_not_last}"
        ),
    )

    revenue = pd.to_numeric(transactions["revenue"], errors="coerce")
    cost = pd.to_numeric(transactions["cost"], errors="coerce")
    spend = pd.to_numeric(marketing["spend"], errors="coerce")
    non_positive_revenue = int((revenue <= 0).sum())
    negative_cost = int((cost < 0).sum())
    negative_spend = int((spend < 0).sum())
    status_value_ranges = (
        "PASS"
        if non_positive_revenue == 0 and negative_cost == 0 and negative_spend == 0
        else "FAIL"
    )
    add_result(
        results,
        "value_range_sanity",
        status_value_ranges,
        (
            f"non_positive_revenue={non_positive_revenue}, "
            f"negative_cost={negative_cost}, negative_spend={negative_spend}"
        ),
    )

    experiment_values = experiments[list(RAW_NONNEGATIVE_COLUMNS["marketing_experiments"])].apply(
        pd.to_numeric, errors="coerce"
    )
    experiment_negative = int((experiment_values < 0).sum().sum())
    experiment_arms = experiments.groupby("experiment_id")["assignment"].nunique()
    experiments_missing_arm = int((experiment_arms != 2).sum())
    price_values = pricing[list(RAW_NONNEGATIVE_COLUMNS["pricing_interventions"])].apply(
        pd.to_numeric, errors="coerce"
    )
    pricing_negative = int((price_values < 0).sum().sum())
    price_ratio = price_values["observed_price"] / price_values["reference_price"]
    expected_ratio = pricing["assignment"].map(
        {"price_down_10": 0.9, "control": 1.0, "price_up_10": 1.1}
    )
    invalid_price_assignments = int((~np.isclose(price_ratio, expected_ratio, atol=1e-8)).sum())
    pricing_cells_missing_arm = int(
        (pricing.groupby(["product_type", "region"])["assignment"].nunique() != 3).sum()
    )
    causal_inputs_ok = (
        experiment_negative == 0
        and experiments_missing_arm == 0
        and pricing_negative == 0
        and invalid_price_assignments == 0
        and pricing_cells_missing_arm == 0
    )
    add_result(
        results,
        "causal_design_input_integrity",
        "PASS" if causal_inputs_ok else "FAIL",
        (
            f"negative_experiment_values={experiment_negative}, "
            f"experiments_missing_arm={experiments_missing_arm}, "
            f"negative_pricing_values={pricing_negative}, "
            f"invalid_price_assignments={invalid_price_assignments}, "
            f"pricing_cells_missing_arm={pricing_cells_missing_arm}"
        ),
    )

    cost_above_revenue = int((cost > revenue).sum())
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

    customer_channels = sorted(customers["acquisition_channel"].dropna().astype(str).unique())
    marketing_channels = sorted(marketing["acquisition_channel"].dropna().astype(str).unique())
    add_result(
        results,
        "channel_domain_alignment",
        "PASS" if customer_channels == marketing_channels else "FAIL",
        f"customer_channels={customer_channels}, marketing_channels={marketing_channels}",
    )

    marketing_dates = pd.to_datetime(marketing["date"], errors="coerce").dropna()
    expected_pairs = len(
        pd.date_range(marketing_dates.min(), marketing_dates.max(), freq="D")
    ) * len(customer_channels)
    observed_pairs = len(marketing.drop_duplicates(["date", "acquisition_channel"]))
    missing_pairs = max(0, expected_pairs - observed_pairs)
    add_result(
        results,
        "marketing_date_channel_coverage",
        "PASS" if missing_pairs == 0 else "FAIL",
        (
            f"expected_pairs={expected_pairs:,}, observed_pairs={observed_pairs:,}, "
            f"missing_pairs={missing_pairs:,}"
        ),
    )

    date_detail = (
        f"customers={_date_range_detail(customers['signup_date'])}, "
        f"transactions={_date_range_detail(transactions['transaction_date'])}, "
        f"marketing={_date_range_detail(marketing['date'])}"
    )
    add_result(
        results,
        "date_coverage_observed",
        "PASS" if invalid_dates == 0 else "FAIL",
        date_detail,
    )

    return pd.DataFrame(results)


def write_outputs(summary: pd.DataFrame) -> None:
    OUT_TABLES_DIR.mkdir(parents=True, exist_ok=True)
    summary.to_csv(OUT_TABLES_DIR / "raw_validation_summary.csv", index=False)


def run() -> None:
    try:
        bundle_manifest = _verify_bundle_if_present()
    except ContractViolation as exc:
        summary = pd.DataFrame(
            [
                {
                    "check_name": "normalized_bundle_integrity",
                    "status": "FAIL",
                    "detail": str(exc),
                }
            ]
        )
        write_outputs(summary)
        raise RawDataValidationError(
            "Raw data validation failed: normalized_bundle_integrity"
        ) from exc

    tables = load_raw_tables()
    summary = build_results(tables)
    if bundle_manifest is not None:
        manifest_tables = bundle_manifest.get("tables")
        table_count = len(manifest_tables) if isinstance(manifest_tables, list) else 0
        bundle_check = pd.DataFrame(
            [
                {
                    "check_name": "normalized_bundle_integrity",
                    "status": "PASS",
                    "detail": (f"bundle_id={bundle_manifest['bundle_id']}, tables={table_count}"),
                }
            ]
        )
        summary = pd.concat([bundle_check, summary], ignore_index=True)
    write_outputs(summary)

    print("Raw data validation completed.")
    print(f"summary_csv: {OUT_TABLES_DIR / 'raw_validation_summary.csv'}")

    failures = summary.loc[summary["status"] == "FAIL", "check_name"].tolist()
    if failures:
        raise RawDataValidationError(
            "Raw data validation failed: " + ", ".join(str(name) for name in failures)
        )


def main() -> None:
    try:
        run()
    except RawDataValidationError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
