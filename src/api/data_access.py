"""Read-only warehouse and analytical-product access for the aggregate API."""

from __future__ import annotations

import re
import threading
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any, ClassVar, Protocol

import duckdb
import pandas as pd

from src.api.config import ApiSettings
from src.paths import PROJECT_ROOT

WAREHOUSE_PATH = PROJECT_ROOT / "outputs" / "warehouse" / "revenue_analytics.duckdb"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
TABLES_DIR = PROJECT_ROOT / "outputs" / "tables"
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class AnalyticsWarehouse(Protocol):
    def ready(self) -> bool: ...

    def coverage(self) -> tuple[date, date]: ...

    def filtered_transactions(
        self,
        start_date: date,
        end_date: date,
        segments: tuple[str, ...],
        regions: tuple[str, ...],
        channels: tuple[str, ...],
        products: tuple[str, ...],
    ) -> pd.DataFrame: ...

    def filtered_customers(
        self,
        start_date: date,
        end_date: date,
        segments: tuple[str, ...],
        regions: tuple[str, ...],
        channels: tuple[str, ...],
    ) -> pd.DataFrame: ...


class AnalyticalProductStore(Protocol):
    def ready(self) -> bool: ...

    def unit_economics(self) -> pd.DataFrame: ...

    def marketing_incrementality(self) -> pd.DataFrame: ...

    def pricing_elasticity(self) -> pd.DataFrame: ...

    def pricing_recommendations(self) -> pd.DataFrame: ...


class SqlAnalyticsWarehouse:
    """Shared parameterized queries across DuckDB and PostgreSQL."""

    def __init__(self, schema: str, placeholder: str) -> None:
        if not IDENTIFIER_PATTERN.fullmatch(schema):
            raise ValueError("warehouse schema must be a simple SQL identifier")
        self.schema = schema
        self.placeholder = placeholder

    def _query(self, sql: str, parameters: list[object] | None = None) -> pd.DataFrame:
        raise NotImplementedError

    def _placeholders(self, values: tuple[str, ...]) -> str:
        return ", ".join(self.placeholder for _ in values)

    def ready(self) -> bool:
        try:
            for relation in ("fct_transactions", "dim_customers"):
                self._query(f"select 1 from {self.schema}.{relation} limit 1")
            start_date, end_date = self.coverage()
            return start_date <= end_date
        except Exception:
            return False

    def coverage(self) -> tuple[date, date]:
        result = self._query(
            f"""
            select
                least(min(transaction_date), min(signup_date)) as coverage_start,
                greatest(max(transaction_date), max(signup_date)) as coverage_end
            from (
                select transaction_date, cast(null as date) as signup_date
                from {self.schema}.fct_transactions
                union all
                select cast(null as date), signup_date
                from {self.schema}.dim_customers
            ) coverage
            """
        )
        if result.empty or pd.isna(result.loc[0, "coverage_start"]):
            raise RuntimeError("warehouse coverage is unavailable")
        return (
            pd.Timestamp(result.loc[0, "coverage_start"]).date(),
            pd.Timestamp(result.loc[0, "coverage_end"]).date(),
        )

    def filtered_transactions(
        self,
        start_date: date,
        end_date: date,
        segments: tuple[str, ...],
        regions: tuple[str, ...],
        channels: tuple[str, ...],
        products: tuple[str, ...],
    ) -> pd.DataFrame:
        query = f"""
            select
                t.transaction_id,
                t.customer_id,
                t.transaction_date,
                t.revenue,
                t.cost,
                t.product_type,
                c.signup_date,
                c.segment,
                c.region,
                c.acquisition_channel
            from {self.schema}.fct_transactions t
            inner join {self.schema}.dim_customers c using (customer_id)
            where t.transaction_date between {self.placeholder} and {self.placeholder}
              and c.segment in ({self._placeholders(segments)})
              and c.region in ({self._placeholders(regions)})
              and c.acquisition_channel in ({self._placeholders(channels)})
              and t.product_type in ({self._placeholders(products)})
            order by t.transaction_date, t.transaction_id
        """
        parameters: list[object] = [start_date, end_date]
        parameters.extend(segments)
        parameters.extend(regions)
        parameters.extend(channels)
        parameters.extend(products)
        return self._query(query, parameters)

    def filtered_customers(
        self,
        start_date: date,
        end_date: date,
        segments: tuple[str, ...],
        regions: tuple[str, ...],
        channels: tuple[str, ...],
    ) -> pd.DataFrame:
        query = f"""
            select customer_id, signup_date, segment, region, acquisition_channel
            from {self.schema}.dim_customers
            where signup_date between {self.placeholder} and {self.placeholder}
              and segment in ({self._placeholders(segments)})
              and region in ({self._placeholders(regions)})
              and acquisition_channel in ({self._placeholders(channels)})
            order by customer_id
        """
        parameters: list[object] = [start_date, end_date]
        parameters.extend(segments)
        parameters.extend(regions)
        parameters.extend(channels)
        return self._query(query, parameters)


class DuckDbAnalyticsWarehouse(SqlAnalyticsWarehouse):
    def __init__(self, path: Path = WAREHOUSE_PATH, schema: str = "analytics_core") -> None:
        super().__init__(schema, "?")
        self.path = path

    def _query(self, sql: str, parameters: list[object] | None = None) -> pd.DataFrame:
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        with duckdb.connect(str(self.path), read_only=True) as connection:
            return connection.execute(sql, parameters or []).fetch_df()


class PostgresAnalyticsWarehouse(SqlAnalyticsWarehouse):
    def __init__(
        self,
        dsn: str,
        schema: str = "analytics_core",
        *,
        connection_factory: Callable[[], Any] | None = None,
    ) -> None:
        if not dsn.strip():
            raise ValueError("PostgreSQL DSN must not be blank")
        super().__init__(schema, "%s")
        self.dsn = dsn
        self.connection_factory = connection_factory or self._connect

    def _connect(self) -> Any:
        import psycopg2

        return psycopg2.connect(self.dsn)

    def _query(self, sql: str, parameters: list[object] | None = None) -> pd.DataFrame:
        connection = self.connection_factory()
        cursor = None
        try:
            set_session = getattr(connection, "set_session", None)
            if callable(set_session):
                set_session(readonly=True, autocommit=True)
            cursor = connection.cursor()
            cursor.execute(sql, parameters or [])
            rows = cursor.fetchall()
            columns = [column[0] for column in cursor.description]
            return pd.DataFrame(rows, columns=columns)
        finally:
            if cursor is not None:
                cursor.close()
            connection.close()


class CsvAnalyticalProductStore:
    """Schema-checked, mtime-aware cache for generated analytical products."""

    _specs: ClassVar[dict[str, tuple[Path, frozenset[str]]]] = {
        "unit_economics": (
            PROCESSED_DIR / "unit_economics.csv",
            frozenset(
                {
                    "acquisition_channel",
                    "customers_acquired",
                    "total_spend",
                    "CAC",
                    "average_LTV",
                    "LTV_to_CAC",
                    "approximate_payback_period",
                    "payback_status",
                    "payback_horizon_months",
                    "payback_mature_customers",
                    "payback_cac",
                }
            ),
        ),
        "marketing_incrementality": (
            TABLES_DIR / "marketing_incrementality.csv",
            frozenset(
                {
                    "experiment_id",
                    "acquisition_channel",
                    "control_customers",
                    "treatment_customers",
                    "identification",
                }
            ),
        ),
        "pricing_elasticity": (
            TABLES_DIR / "pricing_elasticity.csv",
            frozenset(
                {
                    "product_scope",
                    "price_elasticity",
                    "robust_standard_error",
                    "observations",
                }
            ),
        ),
        "pricing_recommendations": (
            TABLES_DIR / "pricing_recommendations.csv",
            frozenset({"product_type", "recommended_price_index", "decision_rule"}),
        ),
    }

    def __init__(
        self,
        processed_dir: Path = PROCESSED_DIR,
        tables_dir: Path = TABLES_DIR,
    ) -> None:
        self.specs = {
            name: (
                (processed_dir if name == "unit_economics" else tables_dir) / path.name,
                columns,
            )
            for name, (path, columns) in self._specs.items()
        }
        self._cache: dict[str, tuple[int, int, pd.DataFrame]] = {}
        self._lock = threading.RLock()

    def _load(self, name: str) -> pd.DataFrame:
        path, required_columns = self.specs[name]
        stat = path.stat()
        if stat.st_size == 0:
            raise RuntimeError(f"analytical product is empty: {path.name}")
        with self._lock:
            cached = self._cache.get(name)
            signature = (stat.st_mtime_ns, stat.st_size)
            if cached is None or cached[:2] != signature:
                frame = pd.read_csv(path)
                missing = sorted(required_columns - set(frame.columns))
                if frame.empty or missing:
                    raise RuntimeError(
                        f"invalid analytical product {path.name}: missing_columns={missing}"
                    )
                self._cache[name] = (*signature, frame)
            return self._cache[name][2].copy()

    def ready(self) -> bool:
        try:
            return all(not self._load(name).empty for name in self.specs)
        except (OSError, UnicodeError, pd.errors.ParserError, RuntimeError):
            return False

    def unit_economics(self) -> pd.DataFrame:
        return self._load("unit_economics")

    def marketing_incrementality(self) -> pd.DataFrame:
        return self._load("marketing_incrementality")

    def pricing_elasticity(self) -> pd.DataFrame:
        return self._load("pricing_elasticity")

    def pricing_recommendations(self) -> pd.DataFrame:
        return self._load("pricing_recommendations")


def build_warehouse(settings: ApiSettings) -> AnalyticsWarehouse:
    if settings.warehouse_backend == "postgres":
        return PostgresAnalyticsWarehouse(settings.postgres_dsn, settings.warehouse_schema)
    return DuckDbAnalyticsWarehouse(Path(settings.duckdb_path), settings.warehouse_schema)
