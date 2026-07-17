# dbt warehouse

This dbt project is the persistent SQL layer for normalized commercial data.

- `dev` uses DuckDB at `outputs/duckdb/revenue_analytics.duckdb`.
- `prod` uses PostgreSQL credentials supplied entirely through environment variables.
- Raw sources default to `data/raw/`; external DuckDB runs set `RAW_DATA_DIR=data/staging`, which resolves the atomic active-bundle pointer.
- Transactions and marketing spend use idempotent `delete+insert` incremental models with a 30-day late-arrival lookback.
- Customers rebuild from the latest normalized snapshot so corrected dimensions are not missed.
- Keys, nullability, customer relationships, composite spend grain, and mart grains are tested by `dbt build`.
- The dashboard exposure and model metadata publish owner and SLA lineage to `outputs/governance/lineage.json`.

Run:

```bash
make warehouse
```

Production first loads the verified six-table bundle with `make load-postgres`. The loader replaces the stable raw-table contents in one advisory-locked transaction and records the active bundle ID. dbt then requires `DBT_TARGET=prod`, `WAREHOUSE_HOST`, `WAREHOUSE_PORT`, `WAREHOUSE_USER`, `DBT_ENV_SECRET_WAREHOUSE_PASSWORD`, `WAREHOUSE_DATABASE`, `WAREHOUSE_SCHEMA`, and the same raw schema in `WAREHOUSE_RAW_SCHEMA`. TLS defaults to `sslmode=require`.

For a controlled backfill, run the project with `--full-refresh` after validating the bounded source window and recording approval. Routine scheduled execution must remain incremental.
