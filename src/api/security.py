"""Constant-time authentication, authorization, and request rate limiting."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from src.api.config import ApiSettings


@dataclass(frozen=True)
class Principal:
    principal_id: str
    scopes: frozenset[str]


class SlidingWindowRateLimiter:
    """Thread-safe single-process limiter for authenticated principals."""

    def __init__(
        self,
        requests_per_minute: int,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if requests_per_minute < 1:
            raise ValueError("requests_per_minute must be positive")
        self.limit = requests_per_minute
        self.clock = clock
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, principal_id: str) -> bool:
        now = self.clock()
        cutoff = now - 60.0
        with self._lock:
            events = self._events[principal_id]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.limit:
                return False
            events.append(now)
            return True


def _basic_credentials(authorization: str) -> tuple[str, str] | None:
    scheme, separator, encoded = authorization.partition(" ")
    if separator != " " or scheme.lower() != "basic":
        return None
    try:
        decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return None
    username, separator, password = decoded.partition(":")
    if separator != ":":
        return None
    return username, password


def authenticate_request(request: Request, required_scope: str) -> Principal:
    settings: ApiSettings = request.app.state.settings
    principal: Principal | None = None
    raw_key = request.headers.get("X-API-Key")
    if raw_key:
        digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        for credential in settings.api_credentials:
            if hmac.compare_digest(digest, credential.sha256_digest):
                principal = Principal(credential.key_id, credential.scopes)
    if principal is None:
        basic = _basic_credentials(request.headers.get("Authorization", ""))
        if basic is not None:
            username, password = basic
            username_ok = hmac.compare_digest(username, settings.dashboard_username)
            password_ok = hmac.compare_digest(password, settings.dashboard_password)
            if username_ok and password_ok:
                principal = Principal(
                    f"dashboard:{username}",
                    frozenset({"dashboard:read", "metrics:read", "schema:read"}),
                )
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
            headers={"WWW-Authenticate": 'Basic realm="Revenue Analytics"'},
        )
    if required_scope not in principal.scopes:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="insufficient scope")
    limiter: SlidingWindowRateLimiter = request.app.state.rate_limiter
    if not limiter.allow(principal.principal_id):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="rate limit exceeded",
            headers={"Retry-After": "60"},
        )
    request.state.principal_id = principal.principal_id
    return principal
