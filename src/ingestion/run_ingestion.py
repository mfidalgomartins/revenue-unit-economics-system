"""Credential-driven ingestion for the complete six-table source contract."""

from __future__ import annotations

import json
import os
from contextlib import ExitStack
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from src.ingestion.adapters import (
    GoogleAdsAdapter,
    GovernedCsvAdapter,
    HubSpotCRMAdapter,
    StripeBillingAdapter,
)
from src.ingestion.publish import publish_normalized_bundle, resolve_current_bundle
from src.paths import PROJECT_ROOT

STAGING_ROOT = PROJECT_ROOT / "data" / "staging"


def _required_environment(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _parse_date(name: str, default: date | None = None) -> date:
    value = os.getenv(name)
    if not value:
        if default is None:
            raise RuntimeError(f"{name} is required for an initial load")
        return default
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must use YYYY-MM-DD") from exc


def _previous_extraction_time(table_name: str) -> datetime | None:
    current_bundle = resolve_current_bundle(STAGING_ROOT)
    if current_bundle is None:
        return None
    manifest_path = current_bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    timestamps = [
        datetime.fromisoformat(str(table["extracted_at"]))
        for table in manifest.get("tables", [])
        if isinstance(table, dict)
        and table.get("table") == table_name
        and table.get("extracted_at")
    ]
    return max(timestamps) if timestamps else None


def _default_start_date(previous_extraction: datetime | None, end_date: date) -> date | None:
    """Keep automatic retries inside the latest closed source window."""
    if previous_extraction is None:
        return None
    return min(previous_extraction.date(), end_date)


def run() -> None:
    customer_checkpoint = _previous_extraction_time("customers")
    transaction_checkpoint = _previous_extraction_time("transactions")
    spend_checkpoint = _previous_extraction_time("marketing_spend")
    end_date = _parse_date(
        "INGESTION_END_DATE",
        default=datetime.now(UTC).date() - timedelta(days=1),
    )
    start_date = _parse_date(
        "INGESTION_START_DATE",
        default=_default_start_date(spend_checkpoint, end_date),
    )
    if start_date > end_date:
        raise RuntimeError("INGESTION_START_DATE must not be after INGESTION_END_DATE")
    try:
        campaign_channel_map = json.loads(_required_environment("GOOGLE_ADS_CHANNEL_MAP"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("GOOGLE_ADS_CHANNEL_MAP must be valid JSON") from exc
    if not isinstance(campaign_channel_map, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in campaign_channel_map.items()
    ):
        raise RuntimeError("GOOGLE_ADS_CHANNEL_MAP must be a string-to-string object")

    extraction_boundary = datetime.now(UTC)
    with ExitStack() as stack:
        hubspot = HubSpotCRMAdapter(
            _required_environment("HUBSPOT_ACCESS_TOKEN"),
            segment_property=os.getenv("HUBSPOT_SEGMENT_PROPERTY", "customer_segment"),
            region_property=os.getenv("HUBSPOT_REGION_PROPERTY", "customer_region"),
            channel_property=os.getenv("HUBSPOT_CHANNEL_PROPERTY", "acquisition_channel"),
        )
        stack.callback(hubspot.close)
        stripe = StripeBillingAdapter(
            _required_environment("STRIPE_SECRET_KEY"),
            _required_environment("STRIPE_API_VERSION"),
            direct_cost_metadata_key=os.getenv(
                "STRIPE_DIRECT_COST_METADATA_KEY", "direct_cost_minor"
            ),
            product_metadata_key=os.getenv("STRIPE_PRODUCT_METADATA_KEY", "product_type"),
            customer_id_metadata_key=os.getenv(
                "STRIPE_CUSTOMER_ID_METADATA_KEY", "crm_customer_id"
            ),
        )
        stack.callback(stripe.close)
        google_ads = GoogleAdsAdapter(
            _required_environment("GOOGLE_ADS_ACCESS_TOKEN"),
            _required_environment("GOOGLE_ADS_DEVELOPER_TOKEN"),
            _required_environment("GOOGLE_ADS_CUSTOMER_ID"),
            campaign_channel_map,
            login_customer_id=os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID"),
            api_version=os.getenv("GOOGLE_ADS_API_VERSION", "v24"),
        )
        stack.callback(google_ads.close)
        governed_csv = GovernedCsvAdapter(Path(_required_environment("GOVERNED_INPUT_DIR")))
        extracted = [
            hubspot.extract(updated_after=customer_checkpoint),
            stripe.extract(paid_after=transaction_checkpoint),
            google_ads.extract(start_date=start_date, end_date=end_date),
            *governed_csv.extract(),
        ]
        results = [replace(result, extracted_at=extraction_boundary) for result in extracted]
        target = publish_normalized_bundle(results, STAGING_ROOT, merge_existing=True)
    print(f"Normalized source bundle published: {target}")


def main() -> None:
    run()


if __name__ == "__main__":
    main()
