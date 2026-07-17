"""Optional PostgreSQL smoke test enabled by CI service credentials."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
from src.api.data_access import PostgresAnalyticsWarehouse
from src.api.service import AggregateDashboardService, DashboardFilters
from src.data_contracts import ACQUISITION_CHANNELS, PRODUCT_TYPES, REGIONS, SEGMENTS
from src.ingestion.adapters import ExtractionResult
from src.ingestion.contracts import CONTRACT_VERSION, NORMALIZED_CONTRACTS
from src.ingestion.load_postgres import PostgresRawLoader
from src.ingestion.publish import publish_normalized_bundle
from src.paths import PROJECT_ROOT
from src.warehouse.run_dbt import run_dbt_build

POSTGRES_TEST_DSN = os.getenv("POSTGRES_TEST_DSN", "")
pytestmark = pytest.mark.skipif(
    not POSTGRES_TEST_DSN,
    reason="POSTGRES_TEST_DSN is only configured in the PostgreSQL smoke job",
)


def test_normalized_bundle_builds_dbt_and_serves_the_aggregate_api(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    extracted_at = datetime(2026, 1, 1, tzinfo=UTC)
    results = []
    for table_name, contract in NORMALIZED_CONTRACTS.items():
        frame = contract.validate(pd.read_csv(PROJECT_ROOT / "data" / "raw" / f"{table_name}.csv"))
        results.append(
            ExtractionResult(
                table_name,
                frame,
                "postgres_smoke_fixture",
                "v1",
                CONTRACT_VERSION,
                extracted_at,
            )
        )
    bundle = publish_normalized_bundle(results, tmp_path, merge_existing=False)
    PostgresRawLoader(POSTGRES_TEST_DSN).load(bundle)

    monkeypatch.setenv("DBT_TARGET", "prod")
    monkeypatch.setenv("WAREHOUSE_HOST", "127.0.0.1")
    monkeypatch.setenv("WAREHOUSE_PORT", "5432")
    monkeypatch.setenv("WAREHOUSE_USER", "postgres")
    monkeypatch.setenv("DBT_ENV_SECRET_WAREHOUSE_PASSWORD", "postgres")
    monkeypatch.setenv("WAREHOUSE_DATABASE", "revenue_analytics")
    monkeypatch.setenv("WAREHOUSE_SCHEMA", "analytics")
    monkeypatch.setenv("WAREHOUSE_RAW_SCHEMA", "raw")
    monkeypatch.setenv("WAREHOUSE_SSLMODE", "disable")
    run_dbt_build(full_refresh=True)

    warehouse = PostgresAnalyticsWarehouse(POSTGRES_TEST_DSN)
    service = AggregateDashboardService(warehouse=warehouse)
    snapshot = service.build_snapshot(
        DashboardFilters(
            start_date=datetime(2023, 1, 1).date(),
            end_date=datetime(2025, 12, 31).date(),
            segments=SEGMENTS,
            regions=REGIONS,
            channels=ACQUISITION_CHANNELS,
            products=PRODUCT_TYPES,
        )
    )

    assert service.ready()
    assert snapshot["monthly"]
    assert int(snapshot["privacy"]["minimumCellSize"]) >= 10
