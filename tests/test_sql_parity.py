"""Execute the reference SQL in sql/ and assert parity with the pipeline.

The SQL files document how the two core feature tables would be built in a
warehouse. Running them with DuckDB against the committed CSVs and comparing
to the pandas pipeline's own outputs keeps that documentation honest: if the
Python transformations and the SQL ever describe different metrics, this
fails.
"""

from __future__ import annotations

import duckdb
import pandas as pd
import pytest
from src.paths import PROJECT_ROOT

SQL_DIR = PROJECT_ROOT / "sql"
RAW = PROJECT_ROOT / "data" / "raw"
PROCESSED = PROJECT_ROOT / "data" / "processed"


@pytest.fixture()
def con() -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect()
    for name in ("customers", "transactions", "marketing_spend"):
        connection.execute(
            f"CREATE VIEW {name} AS SELECT * FROM read_csv_auto('{RAW / f'{name}.csv'}')"
        )
    connection.execute(
        "CREATE VIEW customer_metrics AS SELECT * FROM "
        f"read_csv_auto('{PROCESSED / 'customer_metrics.csv'}')"
    )
    return connection


def test_customer_metrics_sql_matches_pipeline(con: duckdb.DuckDBPyConnection) -> None:
    sql = (SQL_DIR / "customer_metrics.sql").read_text(encoding="utf-8")
    got = con.execute(sql).df().sort_values("customer_id", ignore_index=True)
    expected = pd.read_csv(PROCESSED / "customer_metrics.csv").sort_values(
        "customer_id", ignore_index=True
    )

    assert len(got) == len(expected) == 9000
    for col in ("segment", "region", "acquisition_channel", "transaction_count"):
        assert got[col].tolist() == expected[col].tolist(), col
    for col in (
        "lifetime_days",
        "total_revenue",
        "total_cost",
        "contribution_margin",
        "contribution_margin_pct",
        "avg_revenue_per_transaction",
        "revenue_per_day",
    ):
        pd.testing.assert_series_equal(
            got[col].astype(float),
            expected[col].astype(float),
            check_names=False,
            atol=1e-2,
            rtol=1e-4,
        )


def test_unit_economics_sql_matches_pipeline(con: duckdb.DuckDBPyConnection) -> None:
    sql = (SQL_DIR / "unit_economics.sql").read_text(encoding="utf-8")
    got = con.execute(sql).df().sort_values("acquisition_channel", ignore_index=True)
    expected = pd.read_csv(PROCESSED / "unit_economics.csv").sort_values(
        "acquisition_channel", ignore_index=True
    )

    assert got["acquisition_channel"].tolist() == expected["acquisition_channel"].tolist()
    assert got["customers_acquired"].tolist() == expected["customers_acquired"].tolist()
    for col in (
        "total_spend",
        "CAC",
        "average_LTV",
        "median_LTV",
        "total_channel_contribution_margin",
        "LTV_to_CAC",
        "approximate_payback_period",
    ):
        pd.testing.assert_series_equal(
            got[col].astype(float),
            expected[col].astype(float),
            check_names=False,
            atol=1e-2,
            rtol=1e-4,
        )
