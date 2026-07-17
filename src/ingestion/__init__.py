"""Versioned source adapters for production ingestion."""

from src.ingestion.adapters import (
    GoogleAdsAdapter,
    HubSpotCRMAdapter,
    StripeBillingAdapter,
)
from src.ingestion.contracts import CONTRACT_VERSION, NORMALIZED_CONTRACTS, SourceContract

__all__ = [
    "CONTRACT_VERSION",
    "NORMALIZED_CONTRACTS",
    "GoogleAdsAdapter",
    "HubSpotCRMAdapter",
    "SourceContract",
    "StripeBillingAdapter",
]
