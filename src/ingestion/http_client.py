"""Small retrying HTTP client used by external adapters."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Any

import httpx

RETRYABLE_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})


class SourceRequestError(RuntimeError):
    """Raised when a source request cannot be completed safely."""


class RetryingHttpClient:
    """Bounded exponential retry wrapper with explicit timeout and redacted errors."""

    def __init__(
        self,
        client: httpx.Client,
        *,
        max_attempts: int = 4,
        timeout_seconds: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.client = client
        self.max_attempts = max_attempts
        self.timeout_seconds = timeout_seconds
        self.sleep = sleep

    def request_json(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        json_body: Mapping[str, object] | None = None,
    ) -> Any:
        """Request JSON and retry only transport or explicitly transient failures."""
        last_failure = "unknown failure"
        for attempt in range(1, self.max_attempts + 1):
            delay = min(2.0 ** (attempt - 1), 8.0)
            try:
                response = self.client.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json=json_body,
                    timeout=self.timeout_seconds,
                )
            except httpx.TransportError as exc:
                last_failure = type(exc).__name__
            else:
                if response.status_code < 400:
                    try:
                        return response.json()
                    except ValueError as exc:
                        raise SourceRequestError(f"{method} {url} returned malformed JSON") from exc
                if response.status_code not in RETRYABLE_STATUS_CODES:
                    raise SourceRequestError(
                        f"{method} {url} failed with HTTP {response.status_code}"
                    )
                last_failure = f"HTTP {response.status_code}"
                retry_after = response.headers.get("Retry-After")
                if retry_after is not None:
                    try:
                        delay = min(max(float(retry_after), 0.0), 30.0)
                    except ValueError:
                        delay = min(2.0 ** (attempt - 1), 8.0)

            if attempt < self.max_attempts:
                self.sleep(delay)

        raise SourceRequestError(
            f"{method} {url} failed after {self.max_attempts} attempts ({last_failure})"
        )
