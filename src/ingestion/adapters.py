"""Adapters for commercial systems and governed analytical input drops."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

from src.ingestion.contracts import NORMALIZED_CONTRACTS, ContractViolation
from src.ingestion.http_client import RetryingHttpClient


@dataclass(frozen=True)
class ExtractionResult:
    """A validated normalized table plus source provenance."""

    table_name: str
    frame: pd.DataFrame
    source_name: str
    source_api_version: str
    contract_version: str
    extracted_at: datetime


def _utc_now() -> datetime:
    return datetime.now(UTC)


class GovernedCsvAdapter:
    """Load analytical inputs exported from governed experiment systems."""

    table_names = (
        "marketing_touchpoints",
        "marketing_experiments",
        "pricing_interventions",
    )
    source_name = "governed_csv_drop"
    source_api_version = "csv-v1"

    def __init__(self, source_dir: Path, *, now: Any = _utc_now) -> None:
        self.source_dir = source_dir
        self.now = now

    def extract(self) -> list[ExtractionResult]:
        extracted_at = self.now()
        results: list[ExtractionResult] = []
        for table_name in sorted(self.table_names):
            path = self.source_dir / f"{table_name}.csv"
            if not path.is_file():
                raise ContractViolation(f"governed input is missing {path.name}")
            try:
                frame = pd.read_csv(path)
            except (OSError, UnicodeError, pd.errors.ParserError) as exc:
                raise ContractViolation(
                    f"unable to read governed input {path.name}: {type(exc).__name__}"
                ) from exc
            contract = NORMALIZED_CONTRACTS[table_name]
            results.append(
                ExtractionResult(
                    table_name,
                    contract.validate(frame),
                    self.source_name,
                    self.source_api_version,
                    contract.version,
                    extracted_at,
                )
            )
        return results


class HubSpotCRMAdapter:
    """Normalize HubSpot CRM v3 contacts into the customer master contract."""

    source_name = "hubspot_crm"
    source_api_version = "v3"

    def __init__(
        self,
        token: str,
        *,
        segment_property: str = "customer_segment",
        region_property: str = "customer_region",
        channel_property: str = "acquisition_channel",
        base_url: str = "https://api.hubapi.com",
        client: httpx.Client | None = None,
        now: Any = _utc_now,
    ) -> None:
        if not token.strip():
            raise ValueError("HubSpot token must not be blank")
        self.token = token
        self.segment_property = segment_property
        self.region_property = region_property
        self.channel_property = channel_property
        self._owned_client = client is None
        self.client = client or httpx.Client(base_url=base_url)
        self.http = RetryingHttpClient(self.client)
        self.now = now

    def extract(self, *, updated_after: datetime | None = None) -> ExtractionResult:
        properties = [
            "createdate",
            self.segment_property,
            self.region_property,
            self.channel_property,
        ]
        params: dict[str, object] = {"limit": 100, "properties": ",".join(properties)}

        rows: list[dict[str, object]] = []
        after: str | None = None
        while True:
            if after is not None:
                params["after"] = after
            if updated_after is None:
                payload = self.http.request_json(
                    "GET",
                    "/crm/v3/objects/contacts",
                    headers={"Authorization": f"Bearer {self.token}"},
                    params=params,
                )
            else:
                search_body: dict[str, object] = {
                    "filterGroups": [
                        {
                            "filters": [
                                {
                                    "propertyName": "lastmodifieddate",
                                    "operator": "GTE",
                                    "value": str(int(updated_after.timestamp() * 1000)),
                                }
                            ]
                        }
                    ],
                    "properties": properties,
                    "limit": 100,
                }
                if after is not None:
                    search_body["after"] = after
                payload = self.http.request_json(
                    "POST",
                    "/crm/v3/objects/contacts/search",
                    headers={"Authorization": f"Bearer {self.token}"},
                    json_body=search_body,
                )
            if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
                raise ContractViolation("HubSpot response is missing a results array")
            for item in payload["results"]:
                props = item.get("properties", {}) if isinstance(item, dict) else {}
                rows.append(
                    {
                        "customer_id": str(item.get("id", "")),
                        "signup_date": props.get("createdate"),
                        "segment": props.get(self.segment_property),
                        "region": props.get(self.region_property),
                        "acquisition_channel": props.get(self.channel_property),
                    }
                )
            paging = payload.get("paging", {})
            after_value = paging.get("next", {}).get("after") if isinstance(paging, dict) else None
            if after_value in (None, ""):
                break
            after = str(after_value)

        frame = pd.DataFrame(rows, columns=NORMALIZED_CONTRACTS["customers"].columns)
        normalized = NORMALIZED_CONTRACTS["customers"].validate(
            frame, allow_empty=updated_after is not None
        )
        return ExtractionResult(
            "customers",
            normalized,
            self.source_name,
            self.source_api_version,
            NORMALIZED_CONTRACTS["customers"].version,
            self.now(),
        )

    def close(self) -> None:
        if self._owned_client:
            self.client.close()


class StripeBillingAdapter:
    """Normalize paid Stripe invoices into the transaction ledger contract."""

    source_name = "stripe_billing"

    def __init__(
        self,
        secret_key: str,
        api_version: str,
        *,
        direct_cost_metadata_key: str = "direct_cost_minor",
        product_metadata_key: str = "product_type",
        customer_id_metadata_key: str = "crm_customer_id",
        base_url: str = "https://api.stripe.com",
        client: httpx.Client | None = None,
        now: Any = _utc_now,
    ) -> None:
        if not secret_key.strip() or not api_version.strip():
            raise ValueError("Stripe secret key and API version must not be blank")
        self.secret_key = secret_key
        self.source_api_version = api_version
        self.direct_cost_metadata_key = direct_cost_metadata_key
        self.product_metadata_key = product_metadata_key
        self.customer_id_metadata_key = customer_id_metadata_key
        self._owned_client = client is None
        self.client = client or httpx.Client(base_url=base_url)
        self.http = RetryingHttpClient(self.client)
        self.now = now

    def extract(self, *, paid_after: datetime | None = None) -> ExtractionResult:
        incremental = paid_after is not None
        endpoint = "/v1/events" if incremental else "/v1/invoices"
        params: dict[str, object] = (
            {
                "limit": 100,
                "type": "invoice.paid",
                "created[gte]": int(paid_after.timestamp()),
            }
            if paid_after is not None
            else {"limit": 100, "status": "paid"}
        )
        rows: list[dict[str, object]] = []

        while True:
            payload = self.http.request_json(
                "GET",
                endpoint,
                headers={
                    "Authorization": f"Bearer {self.secret_key}",
                    "Stripe-Version": self.source_api_version,
                },
                params=params,
            )
            if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
                raise ContractViolation("Stripe response is missing a data array")
            page_items = payload["data"]
            invoices: list[dict[str, Any]] = []
            if incremental:
                for event in page_items:
                    if not isinstance(event, dict):
                        raise ContractViolation("Stripe event is not an object")
                    event_data = event.get("data")
                    invoice = event_data.get("object") if isinstance(event_data, dict) else None
                    if not isinstance(invoice, dict):
                        raise ContractViolation("Stripe invoice.paid event is missing its invoice")
                    invoices.append(invoice)
            else:
                for invoice in page_items:
                    if not isinstance(invoice, dict):
                        raise ContractViolation("Stripe invoice is not an object")
                    invoices.append(invoice)
            for invoice in invoices:
                raw_metadata = invoice.get("metadata")
                metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
                raw_status_transitions = invoice.get("status_transitions")
                status_transitions = (
                    raw_status_transitions if isinstance(raw_status_transitions, dict) else {}
                )
                paid_at = status_transitions.get("paid_at")
                rows.append(
                    {
                        "transaction_id": str(invoice.get("id", "")),
                        "customer_id": str(metadata.get(self.customer_id_metadata_key, "")),
                        "transaction_date": datetime.fromtimestamp(
                            int(paid_at or invoice.get("created", 0)), tz=UTC
                        ),
                        "revenue": float(invoice.get("amount_paid", 0)) / 100.0,
                        "cost": float(metadata.get(self.direct_cost_metadata_key, "nan")) / 100.0,
                        "product_type": metadata.get(self.product_metadata_key),
                    }
                )
            if not payload.get("has_more"):
                break
            if not page_items:
                raise ContractViolation("Stripe returned has_more=true with an empty page")
            last_item = page_items[-1]
            if not isinstance(last_item, dict) or not last_item.get("id"):
                raise ContractViolation("Stripe pagination item is missing its ID")
            params["starting_after"] = str(last_item["id"])

        frame = pd.DataFrame(rows, columns=NORMALIZED_CONTRACTS["transactions"].columns)
        if not frame.empty:
            frame = frame.drop_duplicates("transaction_id", keep="last", ignore_index=True)
        normalized = NORMALIZED_CONTRACTS["transactions"].validate(frame, allow_empty=incremental)
        return ExtractionResult(
            "transactions",
            normalized,
            self.source_name,
            self.source_api_version,
            NORMALIZED_CONTRACTS["transactions"].version,
            self.now(),
        )

    def close(self) -> None:
        if self._owned_client:
            self.client.close()


class GoogleAdsAdapter:
    """Normalize Google Ads search-stream spend into the daily channel contract."""

    source_name = "google_ads"

    def __init__(
        self,
        access_token: str,
        developer_token: str,
        customer_id: str,
        campaign_channel_map: dict[str, str],
        *,
        login_customer_id: str | None = None,
        api_version: str = "v24",
        base_url: str = "https://googleads.googleapis.com",
        client: httpx.Client | None = None,
        now: Any = _utc_now,
    ) -> None:
        if not all(
            value.strip() for value in (access_token, developer_token, customer_id, api_version)
        ):
            raise ValueError("Google Ads credentials, customer ID, and API version are required")
        if not campaign_channel_map:
            raise ValueError("campaign_channel_map must not be empty")
        self.access_token = access_token
        self.developer_token = developer_token
        self.customer_id = customer_id.replace("-", "")
        self.campaign_channel_map = campaign_channel_map
        self.login_customer_id = login_customer_id.replace("-", "") if login_customer_id else None
        self.source_api_version = api_version
        self._owned_client = client is None
        self.client = client or httpx.Client(base_url=base_url)
        self.http = RetryingHttpClient(self.client)
        self.now = now

    def extract(self, *, start_date: date, end_date: date) -> ExtractionResult:
        if start_date > end_date:
            raise ValueError("start_date must not be after end_date")
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "developer-token": self.developer_token,
        }
        if self.login_customer_id:
            headers["login-customer-id"] = self.login_customer_id
        query = (
            "SELECT campaign.id, segments.date, metrics.cost_micros "
            "FROM campaign "
            f"WHERE segments.date BETWEEN '{start_date.isoformat()}' AND '{end_date.isoformat()}'"
        )
        payload = self.http.request_json(
            "POST",
            f"/{self.source_api_version}/customers/{self.customer_id}/googleAds:searchStream",
            headers=headers,
            json_body={"query": query},
        )
        chunks = payload if isinstance(payload, list) else [payload]
        rows: list[dict[str, object]] = []
        for chunk in chunks:
            if not isinstance(chunk, dict) or not isinstance(chunk.get("results", []), list):
                raise ContractViolation("Google Ads response contains an invalid stream chunk")
            for result in chunk.get("results", []):
                campaign_id = str(result.get("campaign", {}).get("id", ""))
                if campaign_id not in self.campaign_channel_map:
                    raise ContractViolation(
                        f"Google Ads campaign {campaign_id!r} has no governed channel mapping"
                    )
                rows.append(
                    {
                        "date": result.get("segments", {}).get("date"),
                        "acquisition_channel": self.campaign_channel_map[campaign_id],
                        "spend": float(result.get("metrics", {}).get("costMicros", 0)) / 1_000_000,
                    }
                )

        frame = pd.DataFrame(rows, columns=NORMALIZED_CONTRACTS["marketing_spend"].columns)
        if not frame.empty:
            frame = frame.groupby(["date", "acquisition_channel"], as_index=False, sort=True).agg(
                spend=("spend", "sum")
            )
            frame = frame[list(NORMALIZED_CONTRACTS["marketing_spend"].columns)]
        normalized = NORMALIZED_CONTRACTS["marketing_spend"].validate(frame, allow_empty=True)
        return ExtractionResult(
            "marketing_spend",
            normalized,
            self.source_name,
            self.source_api_version,
            NORMALIZED_CONTRACTS["marketing_spend"].version,
            self.now(),
        )

    def close(self) -> None:
        if self._owned_client:
            self.client.close()
