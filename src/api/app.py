"""FastAPI application factory for authenticated aggregate analytics."""

from __future__ import annotations

import json
import re
import time
import uuid
from collections.abc import Callable
from datetime import date
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse

from src.api.config import ApiSettings
from src.api.data_access import build_warehouse
from src.api.models import DashboardSnapshot, HealthResponse, UnitEconomicsPoint
from src.api.security import Principal, SlidingWindowRateLimiter, authenticate_request
from src.api.service import (
    AggregateDashboardService,
    DashboardFilters,
    PrivacyThresholdError,
)
from src.dashboard_builder.build_dashboard_assets import (
    build_api_bootstrap_payload,
    build_dashboard_html,
)
from src.data_contracts import ACQUISITION_CHANNELS, PRODUCT_TYPES, REGIONS, SEGMENTS

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
CSP = (
    "default-src 'none'; img-src data:; style-src 'unsafe-inline'; "
    "script-src 'unsafe-inline'; font-src data:; connect-src 'self'; "
    "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)


def _scope_dependency(scope: str) -> Callable[[Request], Principal]:
    def dependency(request: Request) -> Principal:
        return authenticate_request(request, scope)

    return dependency


def _bootstrap_html(service: AggregateDashboardService) -> str:
    payload = build_api_bootstrap_payload(
        {
            "meta": service.bootstrap_metadata(),
        }
    )
    return build_dashboard_html(payload, api_mode=True)


def create_app(
    settings: ApiSettings | None = None,
    service: AggregateDashboardService | None = None,
) -> FastAPI:
    """Create an isolated app instance with explicit configuration."""
    resolved_settings = settings or ApiSettings.from_environment()
    resolved_service = service or AggregateDashboardService(
        minimum_cell_size=resolved_settings.minimum_cell_size,
        warehouse=build_warehouse(resolved_settings),
    )
    app = FastAPI(
        title="Revenue Analytics Aggregate API",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = resolved_settings
    app.state.service = resolved_service
    app.state.rate_limiter = SlidingWindowRateLimiter(resolved_settings.requests_per_minute)

    @app.middleware("http")
    async def operational_middleware(request: Request, call_next: Any) -> Any:
        supplied_request_id = request.headers.get("X-Request-ID", "")
        request_id = (
            supplied_request_id
            if REQUEST_ID_PATTERN.fullmatch(supplied_request_id)
            else str(uuid.uuid4())
        )
        request.state.request_id = request_id
        started = time.monotonic()
        response = await call_next(request)
        duration_ms = round((time.monotonic() - started) * 1000, 3)
        response.headers["X-Request-ID"] = request_id
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        print(
            json.dumps(
                {
                    "event": "api_request",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                    "principal_id": getattr(request.state, "principal_id", None),
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            flush=True,
        )
        return response

    @app.exception_handler(PrivacyThresholdError)
    async def privacy_error_handler(_: Request, __: PrivacyThresholdError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "requested aggregate is unavailable"},
        )

    @app.get("/healthz", response_model=HealthResponse, include_in_schema=False)
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.get("/readyz", response_model=HealthResponse, include_in_schema=False)
    def readiness() -> HealthResponse:
        if not resolved_service.ready():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="analytics products are not ready",
            )
        return HealthResponse(status="ready")

    @app.get("/dashboard", response_class=HTMLResponse)
    def dashboard(
        _: Annotated[Principal, Depends(_scope_dependency("dashboard:read"))],
    ) -> HTMLResponse:
        if not resolved_service.ready():
            raise HTTPException(status_code=503, detail="analytics products are not ready")
        return HTMLResponse(_bootstrap_html(resolved_service))

    @app.get("/v1/dashboard/snapshot", response_model=DashboardSnapshot)
    def dashboard_snapshot(
        _: Annotated[Principal, Depends(_scope_dependency("dashboard:read"))],
        start_date: date,
        end_date: date,
        segments: Annotated[list[str] | None, Query()] = None,
        regions: Annotated[list[str] | None, Query()] = None,
        channels: Annotated[list[str] | None, Query()] = None,
        products: Annotated[list[str] | None, Query()] = None,
    ) -> dict[str, Any]:
        try:
            filters = DashboardFilters(
                start_date=start_date,
                end_date=end_date,
                segments=tuple(segments or SEGMENTS),
                regions=tuple(regions or REGIONS),
                channels=tuple(channels or ACQUISITION_CHANNELS),
                products=tuple(products or PRODUCT_TYPES),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return resolved_service.build_snapshot(filters)

    @app.get("/v1/metrics/channels", response_model=list[UnitEconomicsPoint])
    def channel_metrics(
        _: Annotated[Principal, Depends(_scope_dependency("metrics:read"))],
    ) -> list[dict[str, Any]]:
        return resolved_service.channel_metrics()

    @app.get("/v1/measurement/causal")
    def causal_metrics(
        _: Annotated[Principal, Depends(_scope_dependency("metrics:read"))],
    ) -> dict[str, list[dict[str, Any]]]:
        return resolved_service.causal_metrics()

    @app.get("/v1/openapi.json", include_in_schema=False)
    def protected_openapi(
        _: Annotated[Principal, Depends(_scope_dependency("schema:read"))],
    ) -> dict[str, object]:
        return app.openapi()

    return app
