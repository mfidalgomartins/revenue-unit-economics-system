# Authenticated aggregate API

The FastAPI service exposes read-only, privacy-thresholded analytics and serves the existing dashboard in live API mode. The static HTML remains a deterministic synthetic snapshot; `/dashboard` embeds only configuration and governed filter metadata, then retrieves aggregates from the same-origin API.

## Authentication

Programmatic clients use `X-API-Key`. Configure only SHA-256 digests:

```bash
API_KEY="$(openssl rand -hex 32)"
DIGEST="$(printf '%s' "$API_KEY" | .venv/bin/python -m src.api.hash_key)"
export REVENUE_API_KEY_HASHES="{\"reporting\":{\"sha256\":\"$DIGEST\",\"scopes\":[\"dashboard:read\",\"metrics:read\",\"schema:read\"]}}"
```

Browser access uses HTTP Basic authentication:

```bash
export DASHBOARD_USERNAME="analytics-viewer"
export DASHBOARD_PASSWORD="$(openssl rand -base64 32)"
make api
```

Store credentials and webhook secrets in the deployment secret manager. Use TLS at the reverse proxy or load balancer; API keys and Basic credentials must not cross plaintext HTTP outside local development.

## Data backends

DuckDB is the default local backend:

```text
API_WAREHOUSE_BACKEND=duckdb
API_DUCKDB_PATH=outputs/warehouse/revenue_analytics.duckdb
API_WAREHOUSE_SCHEMA=analytics_core
```

PostgreSQL is the production backend:

```text
API_WAREHOUSE_BACKEND=postgres
API_POSTGRES_DSN=postgresql://...
API_WAREHOUSE_SCHEMA=analytics_core
```

Warehouse reads use parameterized SQL. PostgreSQL connections are read-only and closed after each query; deployment credentials should also have database-level `SELECT` privileges only. Generated causal and unit-economics products remain read-only CSV artifacts, loaded through a schema-checked, file-signature-aware in-process cache. A release must mount those files from the same QA-passing pipeline run as the warehouse snapshot.

## Endpoints

| Endpoint | Authentication | Scope | Response |
|---|---|---|---|
| `GET /healthz` | none | — | process liveness only |
| `GET /readyz` | none | — | warehouse query and analytical-product readiness |
| `GET /dashboard` | Basic or API key | `dashboard:read` | API-backed dashboard HTML |
| `GET /v1/dashboard/snapshot` | Basic or API key | `dashboard:read` | filter-aware aggregate view model |
| `GET /v1/metrics/channels` | API key or Basic | `metrics:read` | governed channel economics |
| `GET /v1/measurement/causal` | API key or Basic | `metrics:read` | incrementality, elasticity, and pricing outputs |
| `GET /v1/openapi.json` | API key or Basic | `schema:read` | OpenAPI contract |

Snapshot filters are repeated query parameters: `segments`, `regions`, `channels`, and `products`, plus required ISO `start_date` and `end_date`. Snapshot KPIs and dimensional views are filter-aware. Channel economics are a full-coverage analytical product: they support channel selection only and are suppressed when date, segment, region, or product filters narrow the slice. The `analyticalScope` response field makes that boundary machine-readable.

## Runtime controls

- Authentication comparisons use constant-time digests.
- Unknown credentials return `401`; valid credentials without scope return `403`.
- Request logs contain correlation ID, principal ID, route, status, and duration, never credentials or query results.
- Responses disable caching, framing, MIME sniffing, referrers, and unnecessary browser permissions.
- Cells, experiment arms, and pricing-model samples below the configured minimum population return a non-disclosing `404` or are omitted. Pricing recommendations publish only when their product-level elasticity evidence passes the threshold.
- Readiness executes warehouse queries, validates date coverage, and checks every required analytical artifact and schema.
- The sliding-window limiter is thread-safe and suitable for one process. Multiple replicas require shared rate limiting at the gateway or a distributed store. The gateway must also rate-limit failed and unauthenticated requests before they reach application authentication.

Run production workers behind a health-checked HTTPS proxy. Deny filesystem writes except for platform logs, and deploy the warehouse snapshot and analytical products as one versioned release unit.
