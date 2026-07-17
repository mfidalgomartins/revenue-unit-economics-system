"""Transactional PostgreSQL loader for verified normalized bundles."""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from src.data_contracts import RAW_DATE_COLUMNS, RAW_NUMERIC_COLUMNS, RAW_SCHEMAS
from src.ingestion.publish import verify_bundle
from src.paths import RAW_DATA_DIR

IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
INTEGER_COLUMNS = {"touchpoint_order", "outcome_window_days", "units_sold"}
BOOLEAN_COLUMNS = {"is_conversion_touch", "converted"}
LOCK_NAME = "revenue_analytics_raw_bundle_publication"


def _column_type(table_name: str, column: str) -> str:
    if column in RAW_DATE_COLUMNS[table_name]:
        return "date"
    if column in BOOLEAN_COLUMNS:
        return "boolean"
    if column in INTEGER_COLUMNS:
        return "integer"
    if column in RAW_NUMERIC_COLUMNS[table_name]:
        return "double precision"
    return "text"


def _table_ddl(table_name: str) -> str:
    return ", ".join(
        f"{column} {_column_type(table_name, column)} not null"
        for column in RAW_SCHEMAS[table_name]
    )


class PostgresRawLoader:
    """Load all six raw tables in one transaction without breaking dbt dependencies."""

    def __init__(
        self,
        dsn: str,
        schema: str = "raw",
        *,
        connection_factory: Callable[[], Any] | None = None,
    ) -> None:
        if not dsn.strip():
            raise ValueError("PostgreSQL DSN must not be blank")
        if not IDENTIFIER_PATTERN.fullmatch(schema):
            raise ValueError("PostgreSQL raw schema must be a simple SQL identifier")
        self.dsn = dsn
        self.schema = schema
        self.connection_factory = connection_factory or self._connect

    def _connect(self) -> Any:
        import psycopg2

        return psycopg2.connect(self.dsn)

    def load(self, bundle: Path) -> str:
        manifest = verify_bundle(bundle)
        manifest_tables = cast(list[dict[str, object]], manifest["tables"])
        entries = {str(entry["table"]): entry for entry in manifest_tables}
        connection = self.connection_factory()
        cursor = None
        try:
            cursor = connection.cursor()
            cursor.execute("select pg_advisory_xact_lock(hashtext(%s))", [LOCK_NAME])
            cursor.execute(f"create schema if not exists {self.schema}")

            for table_name in sorted(RAW_SCHEMAS):
                candidate = f"_candidate_{table_name}"
                cursor.execute(f"drop table if exists {self.schema}.{candidate}")
                cursor.execute(f"create table {self.schema}.{candidate} ({_table_ddl(table_name)})")
                columns = ", ".join(RAW_SCHEMAS[table_name])
                copy_sql = (
                    f"COPY {self.schema}.{candidate} ({columns}) "
                    "FROM STDIN WITH (FORMAT CSV, HEADER TRUE)"
                )
                with (bundle / f"{table_name}.csv").open(encoding="utf-8", newline="") as source:
                    cursor.copy_expert(copy_sql, source)
                cursor.execute(f"select count(*) from {self.schema}.{candidate}")
                observed_rows = int(cursor.fetchone()[0])
                expected_rows = cast(int, entries[table_name]["rows"])
                if observed_rows != expected_rows:
                    raise RuntimeError(
                        f"PostgreSQL load count mismatch for {table_name}: "
                        f"expected={expected_rows}, observed={observed_rows}"
                    )

            for table_name in sorted(RAW_SCHEMAS):
                candidate = f"_candidate_{table_name}"
                cursor.execute(
                    f"create table if not exists {self.schema}.{table_name} "
                    f"({_table_ddl(table_name)})"
                )
                cursor.execute(f"truncate table {self.schema}.{table_name}")
                cursor.execute(
                    f"insert into {self.schema}.{table_name} "
                    f"select * from {self.schema}.{candidate}"
                )
                cursor.execute(f"drop table {self.schema}.{candidate}")

            cursor.execute(
                f"""
                create table if not exists {self.schema}._ingestion_publications (
                    bundle_id text primary key,
                    contract_version text not null,
                    table_count integer not null,
                    loaded_at timestamptz not null default current_timestamp
                )
                """
            )
            cursor.execute(
                f"""
                insert into {self.schema}._ingestion_publications
                    (bundle_id, contract_version, table_count)
                values (%s, %s, %s)
                on conflict (bundle_id) do update
                set loaded_at = current_timestamp
                """,
                [manifest["bundle_id"], manifest["contract_version"], len(entries)],
            )
            connection.commit()
            return str(manifest["bundle_id"])
        except Exception:
            connection.rollback()
            raise
        finally:
            if cursor is not None:
                cursor.close()
            connection.close()


def run() -> None:
    dsn = os.getenv("INGESTION_POSTGRES_DSN", "").strip()
    if not dsn:
        raise RuntimeError("INGESTION_POSTGRES_DSN is required")
    schema = os.getenv("WAREHOUSE_RAW_SCHEMA", "raw")
    bundle_id = PostgresRawLoader(dsn, schema).load(RAW_DATA_DIR)
    print(f"PostgreSQL raw bundle loaded: bundle_id={bundle_id}")


def main() -> None:
    run()


if __name__ == "__main__":
    main()
