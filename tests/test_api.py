"""Authentication, privacy, and aggregate API integration tests."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
from datetime import date
from pathlib import Path

import httpx
import pandas as pd
import pytest
import src.api.app as api_app
import src.api.data_access as data_access
import src.api.hash_key as hash_key
from src.api.app import create_app
from src.api.config import ApiCredential, ApiSettings
from src.api.data_access import CsvAnalyticalProductStore, PostgresAnalyticsWarehouse
from src.api.security import SlidingWindowRateLimiter, _basic_credentials
from src.api.service import (
    AggregateDashboardService,
    DashboardFilters,
    PrivacyThresholdError,
)
from src.data_contracts import ACQUISITION_CHANNELS, PRODUCT_TYPES, REGIONS, SEGMENTS

API_KEY = "portfolio-api-key-with-32-characters"


def _settings(
    *,
    scopes: frozenset[str] | None = None,
    requests_per_minute: int = 120,
) -> ApiSettings:
    return ApiSettings(
        api_credentials=(
            ApiCredential(
                "integration-test",
                hashlib.sha256(API_KEY.encode()).hexdigest(),
                scopes or frozenset({"dashboard:read", "metrics:read", "schema:read"}),
            ),
        ),
        dashboard_username="viewer",
        dashboard_password="a-strong-dashboard-password",
        requests_per_minute=requests_per_minute,
    )


async def _request(
    app: object,
    method: str,
    path: str,
    **kwargs: object,
) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as client:
        return await client.request(method, path, **kwargs)


def _full_filters() -> DashboardFilters:
    return DashboardFilters(
        date(2023, 1, 1),
        date(2025, 12, 31),
        SEGMENTS,
        REGIONS,
        ACQUISITION_CHANNELS,
        PRODUCT_TYPES,
    )


def test_api_settings_validate_and_load_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    credential_json = json.dumps(
        {
            "key-1": {
                "sha256": hashlib.sha256(API_KEY.encode()).hexdigest(),
                "scopes": ["metrics:read"],
            }
        }
    )
    monkeypatch.setenv("REVENUE_API_KEY_HASHES", credential_json)
    monkeypatch.setenv("DASHBOARD_USERNAME", "viewer")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "password-with-sufficient-entropy")
    loaded = ApiSettings.from_environment()
    assert loaded.api_credentials[0].key_id == "key-1"

    with pytest.raises(ValueError, match="at least 10"):
        ApiSettings(loaded.api_credentials, "viewer", "password", minimum_cell_size=9)
    bad_digest = ApiCredential("bad", "x", frozenset({"metrics:read"}))
    with pytest.raises(ValueError, match="invalid SHA"):
        ApiSettings((bad_digest,), "viewer", "password")
    duplicate = loaded.api_credentials[0]
    with pytest.raises(ValueError, match="unique"):
        ApiSettings((duplicate, duplicate), "viewer", "password")

    monkeypatch.setenv("REVENUE_API_KEY_HASHES", "not-json")
    with pytest.raises(RuntimeError, match="valid JSON"):
        ApiSettings.from_environment()
    monkeypatch.setenv("REVENUE_API_KEY_HASHES", "[]")
    with pytest.raises(RuntimeError, match="JSON object"):
        ApiSettings.from_environment()

    with pytest.raises(ValueError, match="warehouse backend"):
        ApiSettings(
            loaded.api_credentials,
            "viewer",
            "password",
            warehouse_backend="sqlite",
        )
    with pytest.raises(ValueError, match="PostgreSQL DSN"):
        ApiSettings(
            loaded.api_credentials,
            "viewer",
            "password",
            warehouse_backend="postgres",
        )


def test_basic_parser_and_rate_limiter_boundaries() -> None:
    encoded = base64.b64encode(b"viewer:password").decode()
    assert _basic_credentials(f"Basic {encoded}") == ("viewer", "password")
    assert _basic_credentials("Bearer token") is None
    assert _basic_credentials("Basic invalid!") is None

    times = iter([0.0, 1.0, 2.0, 61.0])
    limiter = SlidingWindowRateLimiter(2, clock=lambda: next(times))
    assert limiter.allow("principal")
    assert limiter.allow("principal")
    assert not limiter.allow("principal")
    assert limiter.allow("principal")
    with pytest.raises(ValueError, match="positive"):
        SlidingWindowRateLimiter(0)


def test_aggregate_service_returns_only_thresholded_view_models() -> None:
    service = AggregateDashboardService()
    snapshot = service.build_snapshot(_full_filters())

    assert service.ready()
    assert len(snapshot["monthly"]) == 36
    assert len(snapshot["histogramBins"]) <= 10
    assert all(row["count"] >= 10 for row in snapshot["histogramBins"])
    assert snapshot["privacy"]["minimumCellSize"] == 10
    channel_metrics = service.channel_metrics()
    assert len(channel_metrics) == 6
    assert all("paybackCAC" in row for row in channel_metrics)
    causal = service.causal_metrics()
    assert set(causal) == {"incrementality", "elasticity", "pricingRecommendations"}


def test_causal_products_enforce_population_thresholds() -> None:
    base = CsvAnalyticalProductStore()

    class Products:
        def ready(self) -> bool:
            return True

        def unit_economics(self) -> pd.DataFrame:
            return base.unit_economics()

        def marketing_incrementality(self) -> pd.DataFrame:
            return pd.DataFrame(
                [
                    {
                        "experiment_id": "small",
                        "acquisition_channel": "email",
                        "control_customers": 9,
                        "treatment_customers": 50,
                    },
                    {
                        "experiment_id": "large",
                        "acquisition_channel": "organic",
                        "control_customers": 50,
                        "treatment_customers": 50,
                    },
                ]
            )

        def pricing_elasticity(self) -> pd.DataFrame:
            return pd.DataFrame(
                [
                    {"product_scope": "Core", "observations": 100},
                    {"product_scope": "Services", "observations": 5},
                ]
            )

        def pricing_recommendations(self) -> pd.DataFrame:
            return pd.DataFrame(
                [
                    {"product_type": "Core", "recommended_price_index": 1.05},
                    {"product_type": "Services", "recommended_price_index": 1.00},
                ]
            )

    causal = AggregateDashboardService(products=Products()).causal_metrics()

    assert [row["experiment_id"] for row in causal["incrementality"]] == ["large"]
    assert [row["product_scope"] for row in causal["elasticity"]] == ["Core"]
    assert [row["product_type"] for row in causal["pricingRecommendations"]] == ["Core"]


def test_filtered_snapshot_does_not_mix_global_unit_economics() -> None:
    service = AggregateDashboardService()
    filters = DashboardFilters(
        date(2023, 1, 1),
        date(2025, 12, 31),
        ("SMB",),
        REGIONS,
        ACQUISITION_CHANNELS,
        PRODUCT_TYPES,
    )

    snapshot = service.build_snapshot(filters)

    assert snapshot["unitEconomics"] == []
    assert snapshot["analyticalScope"]["unitEconomics"] == "suppressed_incompatible_slice"
    assert all(not row["entity"].startswith("Channel:") for row in snapshot["risks"])
    assert snapshot["decision"]["decision"] == "Channel economics unavailable for this slice"
    assert snapshot["decision"]["scale"] == "Not assessed"
    channel_insight = next(
        insight for insight in snapshot["insights"] if insight["title"] == "Channel Efficiency Risk"
    )
    assert channel_insight["badge"] == "Unavailable"
    assert channel_insight["tone"] == "neutral"


def test_aggregate_service_rejects_invalid_and_small_slices(tmp_path: Path) -> None:
    service = AggregateDashboardService()
    with pytest.raises(ValueError, match="unsupported"):
        DashboardFilters(
            date(2023, 1, 1),
            date(2025, 1, 1),
            ("Unknown",),
            REGIONS,
            ACQUISITION_CHANNELS,
            PRODUCT_TYPES,
        )
    with pytest.raises(ValueError, match="after"):
        DashboardFilters(
            date(2025, 1, 2),
            date(2025, 1, 1),
            SEGMENTS,
            REGIONS,
            ACQUISITION_CHANNELS,
            PRODUCT_TYPES,
        )
    small = DashboardFilters(
        date(2025, 12, 31),
        date(2025, 12, 31),
        ("Enterprise",),
        ("LATAM",),
        ("email",),
        ("Services",),
    )
    with pytest.raises(PrivacyThresholdError, match="fewer"):
        service.build_snapshot(small)
    assert not AggregateDashboardService(tmp_path / "missing.duckdb").ready()

    empty_warehouse = tmp_path / "empty.duckdb"
    import duckdb

    duckdb.connect(str(empty_warehouse)).close()
    assert not AggregateDashboardService(empty_warehouse).ready()


def test_postgres_repository_uses_read_only_parameterized_queries() -> None:
    connections: list[object] = []
    executed: list[tuple[str, list[object]]] = []

    class FakeCursor:
        description: list[tuple[str]]
        rows: list[tuple[object, ...]]

        def execute(self, sql: str, parameters: list[object]) -> None:
            executed.append((sql, parameters))
            if "coverage_start" in sql:
                self.description = [("coverage_start",), ("coverage_end",)]
                self.rows = [(date(2023, 1, 1), date(2025, 12, 31))]
            elif "select customer_id" in sql:
                self.description = [
                    ("customer_id",),
                    ("signup_date",),
                    ("segment",),
                    ("region",),
                    ("acquisition_channel",),
                ]
                self.rows = []
            else:
                self.description = [("probe",)]
                self.rows = [(1,)]

        def fetchall(self) -> list[tuple[object, ...]]:
            return self.rows

        def close(self) -> None:
            pass

    class FakeConnection:
        def __init__(self) -> None:
            self.read_only = False
            self.closed = False

        def set_session(self, *, readonly: bool, autocommit: bool) -> None:
            self.read_only = readonly and autocommit

        def cursor(self) -> FakeCursor:
            return FakeCursor()

        def close(self) -> None:
            self.closed = True

    def connect() -> FakeConnection:
        connection = FakeConnection()
        connections.append(connection)
        return connection

    warehouse = PostgresAnalyticsWarehouse("postgresql://redacted", connection_factory=connect)

    assert warehouse.ready()
    warehouse.filtered_customers(
        date(2025, 1, 1),
        date(2025, 1, 31),
        ("SMB",),
        ("EMEA",),
        ("organic",),
    )
    customer_query, parameters = executed[-1]
    assert "%s" in customer_query and "?" not in customer_query
    assert parameters[-3:] == ["SMB", "EMEA", "organic"]
    assert all(connection.read_only and connection.closed for connection in connections)  # type: ignore[attr-defined]


def test_analytical_product_store_reuses_unchanged_frames(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = CsvAnalyticalProductStore()
    first = store.unit_economics()

    monkeypatch.setattr(
        data_access.pd,
        "read_csv",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unexpected reload")),
    )

    second = store.unit_economics()
    assert first.equals(second)


def test_api_auth_scope_privacy_and_security_headers() -> None:
    app = create_app(_settings())
    health = asyncio.run(_request(app, "GET", "/healthz"))
    assert health.status_code == 200
    assert health.headers["x-content-type-options"] == "nosniff"
    assert health.headers["cache-control"] == "no-store"
    ready = asyncio.run(_request(app, "GET", "/readyz"))
    assert ready.status_code == 200

    unauthorized = asyncio.run(_request(app, "GET", "/v1/metrics/channels"))
    assert unauthorized.status_code == 401
    authorized = asyncio.run(
        _request(
            app,
            "GET",
            "/v1/metrics/channels",
            headers={"X-API-Key": API_KEY, "X-Request-ID": "known-request"},
        )
    )
    assert authorized.status_code == 200
    assert authorized.headers["x-request-id"] == "known-request"

    limited_app = create_app(_settings(scopes=frozenset({"dashboard:read"})))
    forbidden = asyncio.run(
        _request(
            limited_app,
            "GET",
            "/v1/metrics/channels",
            headers={"X-API-Key": API_KEY},
        )
    )
    assert forbidden.status_code == 403


def test_api_snapshot_openapi_dashboard_and_rate_limit() -> None:
    app = create_app(_settings(requests_per_minute=20))
    headers = {"X-API-Key": API_KEY}
    snapshot = asyncio.run(
        _request(
            app,
            "GET",
            "/v1/dashboard/snapshot",
            headers=headers,
            params={"start_date": "2023-01-01", "end_date": "2025-12-31"},
        )
    )
    assert snapshot.status_code == 200
    assert snapshot.json()["privacy"]["minimumCellSize"] == 10
    schema = asyncio.run(_request(app, "GET", "/v1/openapi.json", headers=headers))
    assert schema.status_code == 200
    assert schema.json()["info"]["version"] == "1.0.0"

    dashboard = asyncio.run(
        _request(app, "GET", "/dashboard", auth=("viewer", "a-strong-dashboard-password"))
    )
    assert dashboard.status_code == 200
    assert "const API_MODE = true" in dashboard.text
    assert "connect-src 'self'" in dashboard.text
    assert "C0000001" not in dashboard.text

    rate_app = create_app(_settings(requests_per_minute=1))
    first = asyncio.run(_request(rate_app, "GET", "/v1/metrics/channels", headers=headers))
    second = asyncio.run(_request(rate_app, "GET", "/v1/metrics/channels", headers=headers))
    assert first.status_code == 200
    assert second.status_code == 429


def test_api_dashboard_bootstrap_never_loads_raw_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_raw_load() -> None:
        raise AssertionError("raw records must not be loaded for API bootstrap")

    monkeypatch.setattr(api_app, "load_inputs", reject_raw_load, raising=False)
    app = create_app(_settings())

    dashboard = asyncio.run(
        _request(app, "GET", "/dashboard", auth=("viewer", "a-strong-dashboard-password"))
    )

    assert dashboard.status_code == 200
    assert "C0000001" not in dashboard.text


def test_api_returns_non_disclosing_privacy_response() -> None:
    app = create_app(_settings())
    response = asyncio.run(
        _request(
            app,
            "GET",
            "/v1/dashboard/snapshot",
            headers={"X-API-Key": API_KEY},
            params={
                "start_date": "2025-12-31",
                "end_date": "2025-12-31",
                "segments": "Enterprise",
                "regions": "LATAM",
                "channels": "email",
                "products": "Services",
            },
        )
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "requested aggregate is unavailable"}


def test_api_key_hash_utility_never_echoes_secret(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret = "a-long-random-api-key-value-123456"
    monkeypatch.setattr(hash_key.sys, "stdin", io.StringIO(secret + "\n"))
    hash_key.main()
    output = capsys.readouterr().out.strip()
    assert output == hashlib.sha256(secret.encode()).hexdigest()
    assert secret not in output

    monkeypatch.setattr(hash_key.sys, "stdin", io.StringIO("short\n"))
    with pytest.raises(SystemExit, match="at least 24"):
        hash_key.main()
