"""Contract, retry, adapter, and incremental-publication tests."""

from __future__ import annotations

import fcntl
import json
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pandas as pd
import pytest
import src.ingestion.publish as publisher
import src.ingestion.run_ingestion as ingestion_runner
from src.ingestion.adapters import (
    ExtractionResult,
    GoogleAdsAdapter,
    GovernedCsvAdapter,
    HubSpotCRMAdapter,
    StripeBillingAdapter,
)
from src.ingestion.contracts import CONTRACT_VERSION, NORMALIZED_CONTRACTS, ContractViolation
from src.ingestion.http_client import RetryingHttpClient, SourceRequestError
from src.ingestion.load_postgres import PostgresRawLoader
from src.ingestion.publish import (
    publish_normalized_bundle,
    resolve_current_bundle,
    verify_bundle,
)

NOW = datetime(2026, 7, 12, 12, tzinfo=UTC)


def _client(handler: object) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="https://source.test")


def _customers() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "customer_id": ["C1", "C2"],
            "signup_date": [pd.Timestamp("2025-01-01"), pd.Timestamp("2025-01-01")],
            "segment": ["SMB", "SMB"],
            "region": ["EMEA", "EMEA"],
            "acquisition_channel": ["organic", "organic"],
        }
    )


def _transactions() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "transaction_id": ["I1"],
            "customer_id": ["C1"],
            "transaction_date": [pd.Timestamp("2025-01-05")],
            "revenue": [100.0],
            "cost": [40.0],
            "product_type": ["Core"],
        }
    )


def _marketing() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": [pd.Timestamp("2025-01-01")],
            "acquisition_channel": ["organic"],
            "spend": [25.0],
        }
    )


def _touchpoints() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "touchpoint_id": ["TP1"],
            "customer_id": ["C1"],
            "touchpoint_date": [pd.Timestamp("2024-12-20")],
            "acquisition_channel": ["organic"],
            "touchpoint_order": [1],
            "is_conversion_touch": [True],
        }
    )


def _experiments() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "experiment_id": ["EXP1", "EXP1"],
            "customer_id": ["C1", "C2"],
            "acquisition_channel": ["organic", "organic"],
            "assignment": ["treatment", "control"],
            "assigned_date": [pd.Timestamp("2025-01-01"), pd.Timestamp("2025-01-01")],
            "outcome_window_days": [30, 30],
            "converted": [True, False],
            "pre_period_contribution": [10.0, 10.0],
            "observed_contribution": [20.0, 5.0],
        }
    )


def _pricing() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "intervention_id": ["PI1"],
            "week_start": [pd.Timestamp("2025-01-06")],
            "product_type": ["Core"],
            "region": ["EMEA"],
            "assignment": ["control"],
            "reference_price": [100.0],
            "observed_price": [100.0],
            "units_sold": [10],
            "revenue": [1000.0],
            "contribution_margin": [600.0],
        }
    )


def _result(name: str, frame: pd.DataFrame, *, version: str = CONTRACT_VERSION) -> ExtractionResult:
    return ExtractionResult(name, frame, f"source_{name}", "v1", version, NOW)


def _bundle_results(
    *,
    customers: pd.DataFrame | None = None,
    transactions: pd.DataFrame | None = None,
    marketing_spend: pd.DataFrame | None = None,
) -> list[ExtractionResult]:
    return [
        _result("customers", _customers() if customers is None else customers),
        _result("transactions", _transactions() if transactions is None else transactions),
        _result(
            "marketing_spend",
            _marketing() if marketing_spend is None else marketing_spend,
        ),
        _result("marketing_touchpoints", _touchpoints()),
        _result("marketing_experiments", _experiments()),
        _result("pricing_interventions", _pricing()),
    ]


def test_source_contract_canonicalizes_and_rejects_invalid_rows() -> None:
    validated = NORMALIZED_CONTRACTS["customers"].validate(_customers())
    assert validated["signup_date"].dt.tz is None

    bad = _customers().copy()
    bad.loc[0, "customer_id"] = ""
    with pytest.raises(ContractViolation, match="blank"):
        NORMALIZED_CONTRACTS["customers"].validate(bad)
    bad = _customers().copy()
    bad.loc[0, "segment"] = "Unknown"
    with pytest.raises(ContractViolation, match="unexpected"):
        NORMALIZED_CONTRACTS["customers"].validate(bad)
    duplicate = pd.concat([_customers(), _customers()], ignore_index=True)
    with pytest.raises(ContractViolation, match="duplicates"):
        NORMALIZED_CONTRACTS["customers"].validate(duplicate)
    empty = pd.DataFrame(columns=NORMALIZED_CONTRACTS["customers"].columns)
    assert NORMALIZED_CONTRACTS["customers"].validate(empty, allow_empty=True).empty
    with pytest.raises(ContractViolation, match="empty"):
        NORMALIZED_CONTRACTS["customers"].validate(empty)

    signed_experiment = _experiments()
    signed_experiment.loc[0, "pre_period_contribution"] = -5.0
    signed_experiment.loc[1, "observed_contribution"] = -2.0
    assert len(NORMALIZED_CONTRACTS["marketing_experiments"].validate(signed_experiment)) == 2
    signed_pricing = _pricing()
    signed_pricing.loc[0, "contribution_margin"] = -25.0
    assert len(NORMALIZED_CONTRACTS["pricing_interventions"].validate(signed_pricing)) == 1


def test_retrying_http_client_retries_transient_status() -> None:
    responses = iter(
        [
            httpx.Response(429, headers={"Retry-After": "0"}, json={"error": "slow"}),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    sleeps: list[float] = []
    client = _client(lambda _: next(responses))
    result = RetryingHttpClient(client, sleep=sleeps.append).request_json("GET", "/resource")
    assert result == {"ok": True}
    assert sleeps == [0.0]


def test_retrying_http_client_rejects_permanent_and_invalid_responses() -> None:
    client = _client(lambda _: httpx.Response(400, json={"error": "bad"}))
    with pytest.raises(SourceRequestError, match="HTTP 400"):
        RetryingHttpClient(client).request_json("GET", "/resource")
    malformed = _client(lambda _: httpx.Response(200, content=b"not-json"))
    with pytest.raises(SourceRequestError, match="malformed JSON"):
        RetryingHttpClient(malformed).request_json("GET", "/resource")
    exhausted = _client(lambda _: httpx.Response(503, headers={"Retry-After": "invalid"}))
    with pytest.raises(SourceRequestError, match="after 2 attempts"):
        RetryingHttpClient(exhausted, max_attempts=2, sleep=lambda _: None).request_json(
            "GET", "/resource"
        )
    with pytest.raises(ValueError, match="at least"):
        RetryingHttpClient(client, max_attempts=0)


def test_hubspot_adapter_paginates_and_normalizes_contacts() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        after = request.url.params.get("after")
        if after is None:
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": "C1",
                            "properties": {
                                "createdate": "2025-01-01T00:00:00Z",
                                "customer_segment": "SMB",
                                "customer_region": "EMEA",
                                "acquisition_channel": "organic",
                            },
                        }
                    ],
                    "paging": {"next": {"after": "next"}},
                },
            )
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": "C2",
                        "properties": {
                            "createdate": "2025-01-02T00:00:00Z",
                            "customer_segment": "Startup",
                            "customer_region": "APAC",
                            "acquisition_channel": "paid_search",
                        },
                    }
                ]
            },
        )

    adapter = HubSpotCRMAdapter("token", client=_client(handler), now=lambda: NOW)
    result = adapter.extract()
    assert result.frame["customer_id"].tolist() == ["C1", "C2"]
    assert result.contract_version == CONTRACT_VERSION
    adapter.close()


def test_hubspot_incremental_search_allows_noop_delta() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": []})

    adapter = HubSpotCRMAdapter("token", client=_client(handler), now=lambda: NOW)
    result = adapter.extract(updated_after=datetime(2026, 1, 1, tzinfo=UTC))
    assert result.frame.empty
    assert requests[0].url.path.endswith("/search")
    assert json.loads(requests[0].content)["filterGroups"]


def test_stripe_adapter_uses_governed_metadata_and_paginates() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        invoice = {
            "id": f"I{calls}",
            "created": 1736035200 + calls,
            "amount_paid": 10000,
            "metadata": {
                "crm_customer_id": "C1",
                "direct_cost_minor": "4000",
                "product_type": "Core",
            },
            "status_transitions": {"paid_at": 1736035200 + calls},
        }
        return httpx.Response(
            200,
            json={"data": [invoice], "has_more": calls == 1},
        )

    adapter = StripeBillingAdapter(
        "secret", "2026-06-30.test", client=_client(handler), now=lambda: NOW
    )
    result = adapter.extract()
    assert len(result.frame) == 2
    assert result.frame["revenue"].tolist() == [100.0, 100.0]
    assert result.frame["cost"].tolist() == [40.0, 40.0]


def test_stripe_incremental_uses_paid_events_for_late_paid_invoices() -> None:
    checkpoint = datetime(2026, 1, 1, tzinfo=UTC)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        invoice = {
            "id": "I-LATE",
            "created": int(datetime(2025, 12, 1, tzinfo=UTC).timestamp()),
            "amount_paid": 12000,
            "metadata": {
                "crm_customer_id": "C1",
                "direct_cost_minor": "5000",
                "product_type": "Core",
            },
            "status_transitions": {"paid_at": int(datetime(2026, 1, 2, tzinfo=UTC).timestamp())},
        }
        return httpx.Response(
            200,
            json={
                "data": [{"id": "evt_1", "data": {"object": invoice}}],
                "has_more": False,
            },
        )

    adapter = StripeBillingAdapter(
        "secret", "2026-06-30.test", client=_client(handler), now=lambda: NOW
    )
    result = adapter.extract(paid_after=checkpoint)

    assert requests[0].url.path == "/v1/events"
    assert requests[0].url.params["type"] == "invoice.paid"
    assert requests[0].url.params["created[gte]"] == str(int(checkpoint.timestamp()))
    assert result.frame["transaction_id"].tolist() == ["I-LATE"]
    assert result.frame["transaction_date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-01-02"]


def test_google_ads_adapter_aggregates_mapped_campaigns() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        return httpx.Response(
            200,
            json=[
                {
                    "results": [
                        {
                            "campaign": {"id": "1"},
                            "segments": {"date": "2025-01-01"},
                            "metrics": {"costMicros": "1500000"},
                        },
                        {
                            "campaign": {"id": "2"},
                            "segments": {"date": "2025-01-01"},
                            "metrics": {"costMicros": "2500000"},
                        },
                    ]
                }
            ],
        )

    adapter = GoogleAdsAdapter(
        "access",
        "developer",
        "123-456",
        {"1": "paid_search", "2": "paid_search"},
        client=_client(handler),
        now=lambda: NOW,
    )
    result = adapter.extract(start_date=date(2025, 1, 1), end_date=date(2025, 1, 2))
    assert len(result.frame) == 1
    assert result.frame.loc[0, "spend"] == 4.0
    with pytest.raises(ValueError, match="after"):
        adapter.extract(start_date=date(2025, 1, 2), end_date=date(2025, 1, 1))


def test_google_ads_adapter_requires_explicit_campaign_mapping() -> None:
    client = _client(
        lambda _: httpx.Response(
            200,
            json=[
                {
                    "results": [
                        {
                            "campaign": {"id": "unknown"},
                            "segments": {"date": "2025-01-01"},
                            "metrics": {"costMicros": "1"},
                        }
                    ]
                }
            ],
        )
    )
    adapter = GoogleAdsAdapter("a", "d", "1", {"known": "organic"}, client=client)
    with pytest.raises(ContractViolation, match="no governed channel mapping"):
        adapter.extract(start_date=date(2025, 1, 1), end_date=date(2025, 1, 1))


def test_governed_csv_adapter_validates_the_complete_analytical_input_drop(
    tmp_path: Path,
) -> None:
    frames = {
        "marketing_touchpoints": _touchpoints(),
        "marketing_experiments": _experiments(),
        "pricing_interventions": _pricing(),
    }
    for table_name, frame in frames.items():
        frame.to_csv(tmp_path / f"{table_name}.csv", index=False)

    results = GovernedCsvAdapter(tmp_path, now=lambda: NOW).extract()

    assert [result.table_name for result in results] == sorted(frames)
    assert all(result.contract_version == CONTRACT_VERSION for result in results)
    (tmp_path / "pricing_interventions.csv").unlink()
    with pytest.raises(ContractViolation, match=r"pricing_interventions\.csv"):
        GovernedCsvAdapter(tmp_path).extract()


def test_publish_bundle_validates_references_versions_and_incremental_merge(tmp_path: Path) -> None:
    first_target = publish_normalized_bundle(_bundle_results(), tmp_path, merge_existing=False)
    assert (
        json.loads((first_target / "manifest.json").read_text())["contract_version"]
        == CONTRACT_VERSION
    )
    assert resolve_current_bundle(tmp_path) == first_target

    changed = _marketing().copy()
    changed.loc[0, "spend"] = 30.0
    second_results = _bundle_results(
        customers=pd.DataFrame(columns=_customers().columns),
        transactions=pd.DataFrame(columns=_transactions().columns),
        marketing_spend=changed,
    )
    second_results[3] = _result(
        "marketing_touchpoints", pd.DataFrame(columns=_touchpoints().columns)
    )
    second_results[4] = _result(
        "marketing_experiments", pd.DataFrame(columns=_experiments().columns)
    )
    second_results[5] = _result("pricing_interventions", pd.DataFrame(columns=_pricing().columns))
    second_target = publish_normalized_bundle(
        second_results,
        tmp_path,
        merge_existing=True,
    )
    assert second_target != first_target
    assert pd.read_csv(first_target / "marketing_spend.csv").loc[0, "spend"] == 25.0
    assert pd.read_csv(second_target / "marketing_spend.csv").loc[0, "spend"] == 30.0
    assert resolve_current_bundle(tmp_path) == second_target
    assert verify_bundle(second_target)["bundle_id"] == second_target.name

    orphan = _transactions().assign(customer_id="missing")
    with pytest.raises(ContractViolation, match="unknown customer"):
        publish_normalized_bundle(
            _bundle_results(transactions=orphan),
            tmp_path / "orphan",
            merge_existing=False,
        )
    with pytest.raises(ContractViolation, match="contract version"):
        publish_normalized_bundle(
            [
                _result("customers", _customers(), version="2.0.0"),
                *_bundle_results()[1:],
            ],
            tmp_path / "version",
            merge_existing=False,
        )
    with pytest.raises(ContractViolation, match="bundle mismatch"):
        publish_normalized_bundle([_result("customers", _customers())], tmp_path / "missing")

    (second_target / "marketing_spend.csv").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(ContractViolation, match="digest"):
        verify_bundle(second_target)
    with pytest.raises(ContractViolation, match="digest"):
        publish_normalized_bundle(
            _bundle_results(marketing_spend=_marketing().assign(spend=35.0)),
            tmp_path,
            merge_existing=True,
        )


def test_publication_holds_an_exclusive_lock_through_activation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operations: list[int] = []
    monkeypatch.setattr(
        publisher.fcntl,
        "flock",
        lambda _descriptor, operation: operations.append(operation),
    )

    publish_normalized_bundle(_bundle_results(), tmp_path, merge_existing=False)

    assert operations == [fcntl.LOCK_EX, fcntl.LOCK_UN]


def test_failed_bundle_write_preserves_the_active_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    first_target = publish_normalized_bundle(_bundle_results(), tmp_path, merge_existing=False)
    original_write_text = Path.write_text

    def fail_during_bundle_write(path: Path, *args: object, **kwargs: object) -> int:
        if path.name == "transactions.csv" and "bundles" in path.parts:
            raise OSError("disk full")
        return original_write_text(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "write_text", fail_during_bundle_write)
    with pytest.raises(OSError, match="disk full"):
        publish_normalized_bundle(
            _bundle_results(marketing_spend=_marketing().assign(spend=40.0)),
            tmp_path,
            merge_existing=False,
        )

    assert resolve_current_bundle(tmp_path) == first_target
    assert list((tmp_path / "v1" / "bundles").iterdir()) == [first_target]


def test_postgres_loader_stages_and_swaps_the_complete_bundle_transactionally(
    tmp_path: Path,
) -> None:
    bundle = publish_normalized_bundle(_bundle_results(), tmp_path, merge_existing=False)
    statements: list[str] = []
    copies: list[str] = []

    class FakeCursor:
        def __init__(self) -> None:
            self.copied_rows = 0

        def execute(self, sql: str, parameters: object = None) -> None:
            del parameters
            statements.append(" ".join(sql.split()))

        def copy_expert(self, sql: str, source: object) -> None:
            copies.append(sql)
            self.copied_rows = sum(1 for _line in source) - 1  # type: ignore[union-attr]

        def fetchone(self) -> tuple[object]:
            if statements[-1].lower().startswith("select count"):
                return (self.copied_rows,)
            return (None,)

        def close(self) -> None:
            pass

    class FakeConnection:
        def __init__(self) -> None:
            self.committed = False
            self.rolled_back = False
            self.closed = False
            self.cursor_instance = FakeCursor()

        def cursor(self) -> FakeCursor:
            return self.cursor_instance

        def commit(self) -> None:
            self.committed = True

        def rollback(self) -> None:
            self.rolled_back = True

        def close(self) -> None:
            self.closed = True

    connection = FakeConnection()
    loaded_id = PostgresRawLoader(
        "postgresql://redacted",
        connection_factory=lambda: connection,
    ).load(bundle)

    assert loaded_id == bundle.name
    assert len(copies) == 6
    assert all("COPY raw._candidate_" in copy for copy in copies)
    assert any("pg_advisory_xact_lock" in statement for statement in statements)
    assert connection.committed and not connection.rolled_back and connection.closed


def test_environment_ingestion_runner_builds_and_publishes_all_adapters(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    closed: list[str] = []

    class FakeHubSpot:
        def __init__(self, *_: object, **__: object) -> None:
            pass

        def extract(self, **_: object) -> ExtractionResult:
            return _result("customers", _customers())

        def close(self) -> None:
            closed.append("hubspot")

    class FakeStripe:
        def __init__(self, *_: object, **__: object) -> None:
            pass

        def extract(self, **_: object) -> ExtractionResult:
            return _result("transactions", _transactions())

        def close(self) -> None:
            closed.append("stripe")

    class FakeGoogleAds:
        def __init__(self, *_: object, **__: object) -> None:
            pass

        def extract(self, **_: object) -> ExtractionResult:
            return _result("marketing_spend", _marketing())

        def close(self) -> None:
            closed.append("google")

    class FakeGovernedCsv:
        def __init__(self, *_: object, **__: object) -> None:
            pass

        def extract(self) -> list[ExtractionResult]:
            return [
                _result("marketing_touchpoints", _touchpoints()),
                _result("marketing_experiments", _experiments()),
                _result("pricing_interventions", _pricing()),
            ]

    environment = {
        "INGESTION_START_DATE": "2025-01-01",
        "INGESTION_END_DATE": "2025-01-31",
        "HUBSPOT_ACCESS_TOKEN": "hubspot",
        "STRIPE_SECRET_KEY": "stripe",
        "STRIPE_API_VERSION": "2026-test",
        "GOOGLE_ADS_ACCESS_TOKEN": "access",
        "GOOGLE_ADS_DEVELOPER_TOKEN": "developer",
        "GOOGLE_ADS_CUSTOMER_ID": "123",
        "GOOGLE_ADS_CHANNEL_MAP": '{"1":"paid_search"}',
        "GOVERNED_INPUT_DIR": str(tmp_path / "governed"),
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(ingestion_runner, "STAGING_ROOT", tmp_path)
    monkeypatch.setattr(ingestion_runner, "HubSpotCRMAdapter", FakeHubSpot)
    monkeypatch.setattr(ingestion_runner, "StripeBillingAdapter", FakeStripe)
    monkeypatch.setattr(ingestion_runner, "GoogleAdsAdapter", FakeGoogleAds)
    monkeypatch.setattr(ingestion_runner, "GovernedCsvAdapter", FakeGovernedCsv)
    monkeypatch.setattr(
        ingestion_runner,
        "publish_normalized_bundle",
        lambda results, root, merge_existing: tmp_path,
    )

    ingestion_runner.run()

    assert closed == ["google", "stripe", "hubspot"]


def test_ingestion_closes_partially_constructed_adapters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed: list[str] = []

    class FakeHubSpot:
        def __init__(self, *_: object, **__: object) -> None:
            pass

        def close(self) -> None:
            closed.append("hubspot")

    class FailingStripe:
        def __init__(self, *_: object, **__: object) -> None:
            raise RuntimeError("constructor failed")

    environment = {
        "INGESTION_START_DATE": "2025-01-01",
        "INGESTION_END_DATE": "2025-01-31",
        "HUBSPOT_ACCESS_TOKEN": "hubspot",
        "STRIPE_SECRET_KEY": "stripe",
        "STRIPE_API_VERSION": "2026-test",
        "GOOGLE_ADS_CHANNEL_MAP": '{"1":"paid_search"}',
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(ingestion_runner, "HubSpotCRMAdapter", FakeHubSpot)
    monkeypatch.setattr(ingestion_runner, "StripeBillingAdapter", FailingStripe)

    with pytest.raises(RuntimeError, match="constructor failed"):
        ingestion_runner.run()

    assert closed == ["hubspot"]


def test_ingestion_runner_validates_environment_and_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("MISSING_VARIABLE", raising=False)
    with pytest.raises(RuntimeError, match="required"):
        ingestion_runner._required_environment("MISSING_VARIABLE")
    monkeypatch.setenv("BAD_DATE", "July 12")
    with pytest.raises(RuntimeError, match="YYYY-MM-DD"):
        ingestion_runner._parse_date("BAD_DATE")

    bundle = tmp_path / "v1" / "bundles" / "bundle-1"
    bundle.mkdir(parents=True)
    (bundle / "manifest.json").write_text(
        json.dumps(
            {
                "tables": [
                    {
                        "table": "customers",
                        "extracted_at": "2026-01-01T00:00:00+00:00",
                    },
                    {
                        "table": "transactions",
                        "extracted_at": "2026-01-02T00:00:00+00:00",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "v1" / "current.json").write_text(
        json.dumps({"bundle": "bundles/bundle-1", "contract_version": CONTRACT_VERSION}),
        encoding="utf-8",
    )
    monkeypatch.setattr(ingestion_runner, "STAGING_ROOT", tmp_path)
    assert ingestion_runner._previous_extraction_time("customers") == datetime(
        2026, 1, 1, tzinfo=UTC
    )
    assert ingestion_runner._previous_extraction_time("transactions") == datetime(
        2026, 1, 2, tzinfo=UTC
    )
    assert ingestion_runner._previous_extraction_time("marketing_spend") is None


def test_same_day_ingestion_retry_reuses_the_latest_closed_source_date() -> None:
    previous = datetime(2026, 1, 2, 6, tzinfo=UTC)

    assert ingestion_runner._default_start_date(previous, date(2026, 1, 1)) == date(2026, 1, 1)
    assert ingestion_runner._default_start_date(previous, date(2026, 1, 2)) == date(2026, 1, 2)
    assert ingestion_runner._default_start_date(None, date(2026, 1, 2)) is None
