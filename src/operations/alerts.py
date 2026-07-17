"""Structured local and signed-webhook operational alert sinks."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from typing import Protocol

import httpx

from src.ingestion.http_client import RetryingHttpClient


class AlertSink(Protocol):
    def send(self, event: Mapping[str, object]) -> None:
        """Deliver one non-secret operational event."""


class JsonLogAlertSink:
    """Emit canonical JSON suitable for log collection and routing."""

    def send(self, event: Mapping[str, object]) -> None:
        print(json.dumps(dict(event), sort_keys=True, separators=(",", ":")), flush=True)


class SignedWebhookAlertSink:
    """Deliver alerts with a SHA-256 HMAC signature and bounded retries."""

    def __init__(
        self,
        url: str,
        signing_secret: str,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        if not url.startswith("https://"):
            raise ValueError("alert webhook must use HTTPS")
        if not signing_secret:
            raise ValueError("alert signing secret must not be blank")
        self.url = url
        self.signing_secret = signing_secret.encode("utf-8")
        self._owned_client = client is None
        self.client = client or httpx.Client()
        self.http = RetryingHttpClient(self.client)

    def send(self, event: Mapping[str, object]) -> None:
        payload = json.dumps(dict(event), sort_keys=True, separators=(",", ":"))
        signature = hmac.new(
            self.signing_secret,
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        self.http.request_json(
            "POST",
            self.url,
            headers={
                "Content-Type": "application/json",
                "X-Revenue-Signature-256": f"sha256={signature}",
            },
            json_body=dict(event),
        )

    def close(self) -> None:
        if self._owned_client:
            self.client.close()
