"""Fail-closed API configuration loaded from environment variables."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from src.paths import PROJECT_ROOT


@dataclass(frozen=True)
class ApiCredential:
    key_id: str
    sha256_digest: str
    scopes: frozenset[str]


@dataclass(frozen=True)
class ApiSettings:
    api_credentials: tuple[ApiCredential, ...]
    dashboard_username: str
    dashboard_password: str
    minimum_cell_size: int = 10
    requests_per_minute: int = 120
    warehouse_backend: str = "duckdb"
    duckdb_path: str = str(PROJECT_ROOT / "outputs" / "warehouse" / "revenue_analytics.duckdb")
    postgres_dsn: str = ""
    warehouse_schema: str = "analytics_core"

    def __post_init__(self) -> None:
        if not self.api_credentials:
            raise ValueError("at least one API credential is required")
        if not self.dashboard_username or not self.dashboard_password:
            raise ValueError("dashboard Basic Auth credentials are required")
        if self.minimum_cell_size < 10:
            raise ValueError("minimum_cell_size must be at least 10")
        if self.requests_per_minute < 1:
            raise ValueError("requests_per_minute must be positive")
        if self.warehouse_backend not in {"duckdb", "postgres"}:
            raise ValueError("warehouse backend must be 'duckdb' or 'postgres'")
        if self.warehouse_backend == "duckdb" and not self.duckdb_path.strip():
            raise ValueError("DuckDB path must not be blank")
        if self.warehouse_backend == "postgres" and not self.postgres_dsn.strip():
            raise ValueError("PostgreSQL DSN is required for the postgres warehouse backend")
        identifiers = [credential.key_id for credential in self.api_credentials]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("API credential IDs must be unique")
        for credential in self.api_credentials:
            if len(credential.sha256_digest) != 64:
                raise ValueError(f"credential {credential.key_id!r} has an invalid SHA-256 digest")
            try:
                bytes.fromhex(credential.sha256_digest)
            except ValueError as exc:
                raise ValueError(f"credential {credential.key_id!r} has a non-hex digest") from exc
            if not credential.scopes:
                raise ValueError(f"credential {credential.key_id!r} requires at least one scope")

    @classmethod
    def from_environment(cls) -> ApiSettings:
        raw_credentials = os.getenv("REVENUE_API_KEY_HASHES", "")
        if not raw_credentials:
            raise RuntimeError("REVENUE_API_KEY_HASHES is required")
        try:
            parsed = json.loads(raw_credentials)
        except json.JSONDecodeError as exc:
            raise RuntimeError("REVENUE_API_KEY_HASHES must be valid JSON") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError("REVENUE_API_KEY_HASHES must be a JSON object")
        credentials: list[ApiCredential] = []
        for key_id, config in sorted(parsed.items()):
            if not isinstance(config, dict):
                raise RuntimeError(f"credential {key_id!r} must be an object")
            scopes = config.get("scopes")
            if not isinstance(scopes, list) or not all(isinstance(scope, str) for scope in scopes):
                raise RuntimeError(f"credential {key_id!r} scopes must be a string list")
            credentials.append(
                ApiCredential(
                    str(key_id),
                    str(config.get("sha256", "")).lower(),
                    frozenset(scopes),
                )
            )
        return cls(
            api_credentials=tuple(credentials),
            dashboard_username=os.getenv("DASHBOARD_USERNAME", ""),
            dashboard_password=os.getenv("DASHBOARD_PASSWORD", ""),
            minimum_cell_size=int(os.getenv("MINIMUM_PRIVACY_CELL_SIZE", "10")),
            requests_per_minute=int(os.getenv("API_REQUESTS_PER_MINUTE", "120")),
            warehouse_backend=os.getenv("API_WAREHOUSE_BACKEND", "duckdb").lower(),
            duckdb_path=os.getenv(
                "API_DUCKDB_PATH",
                str(PROJECT_ROOT / "outputs" / "warehouse" / "revenue_analytics.duckdb"),
            ),
            postgres_dsn=os.getenv("API_POSTGRES_DSN", ""),
            warehouse_schema=os.getenv("API_WAREHOUSE_SCHEMA", "analytics_core"),
        )
