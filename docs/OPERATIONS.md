# Operations runbook

## Pipeline profiles

The canonical stage graph in `src/operations/pipeline_spec.py` has two source profiles:

- `synthetic` (default) regenerates the six deterministic source tables before validation;
- `external` requires an explicit `RAW_DATA_DIR` and begins at validation, so production data cannot be overwritten by the generator.

The profiles are mutually exclusive: a synthetic run rejects any configured `RAW_DATA_DIR`, and the generator always writes only to `data/raw`.

Prepare the external source bundle separately, then orchestrate it:

```bash
make ingest
PIPELINE_PROFILE=external RAW_DATA_DIR=data/staging make orchestrate
```

For PostgreSQL, run `make load-postgres` after ingestion and before the `DBT_TARGET=prod` pipeline.

## Scheduled execution

`ops/schedule.cron` runs daily at 06:00 UTC. Install it under the deployment service account after setting `REVENUE_ANALYTICS_HOME` to the release directory. The Linux host must provide `flock` from `util-linux`. The cron entry calls `ops/run_scheduled_pipeline.sh`, which creates the operational state directory and takes a non-blocking lock before invoking `make orchestrate`. A concurrent run exits with status `75` instead of overlapping.

The orchestrator validates the dependency graph, executes modules in isolated process groups, retries only eligible stages, records attempts in `outputs/operations/pipeline_runs.sqlite`, and emits structured JSON. Each stage has an SLA and a hard timeout; the default timeout is twice its SLA. On timeout, the complete process group receives `SIGTERM`, then `SIGKILL` after a five-second grace period. The failure is persisted and alerted, so a hung child cannot hold the schedule lock indefinitely. The run is always finalized and alert transports are always closed, even when a stage or alert sink fails. Mutable run state is ignored by Git; deterministic lineage and SLA definitions are published under `outputs/governance/` with the active pipeline profile.

## Service objectives

The authoritative catalog is `config/operational_slas.json`:

- pipeline availability: 99%;
- daily completion deadline: 08:00 UTC;
- total duration: at most 15 minutes;
- dashboard and unit-economics freshness: at most 26 hours;
- causal and report freshness: at most 168 hours;
- aggregate API availability: 99.9%;
- API p95 latency: at most 500 ms;
- privacy cell size: at least 10.

Stage SLAs, hard timeouts, and retry counts live in `src/operations/pipeline_spec.py`. Change them only with an owner, measured run-duration evidence, and regression tests.

## Alerts

Canonical JSON alerts always go to standard output. Configure both variables to add signed webhook delivery:

```text
ALERT_WEBHOOK_URL
ALERT_WEBHOOK_SIGNING_SECRET
```

The webhook must use HTTPS. Payloads are signed in `X-Revenue-Signature-256` with HMAC-SHA-256. Delivery is best effort: a failing sink emits a structured transport error, does not stop other sinks, and cannot mask the pipeline's terminal status. Alerts include run ID, stage, attempt, duration, SLA, and error type; they exclude exception messages, data rows, and secrets.

## Incident actions

| Event | First checks | Recovery |
|---|---|---|
| source contract failure | vendor version, required metadata, governed CSV files, channel mapping | correct source or mapping; rerun the same bounded window |
| bundle verification failure | active pointer, manifest identity, row counts, file digest | restore the previous immutable pointer; do not edit a bundle in place |
| PostgreSQL raw-load failure | candidate load counts, permissions, advisory-lock holder | correct the cause and rerun; the failed transaction leaves all stable tables unchanged |
| dbt test failure | failing model/test, source row counts, late-arrival window | repair source or model; use `--full-refresh` only for an approved backfill |
| stage retry exhausted | attempts and error type in SQLite, dependency availability | fix the root cause and rerun; do not publish partial downstream outputs |
| SLA breach | stage duration trend, warehouse scan volume, renderer duration | profile before optimizing; revise the SLA only with measured evidence |
| API readiness failure | warehouse query, release-matched analytical files, permissions | restore one complete QA-passing release unit |
| privacy threshold response | requested dimensions and date range | broaden the slice; never lower the threshold ad hoc |

## Backfill and rollback

Backfills set explicit `INGESTION_START_DATE` and `INGESTION_END_DATE`, then run ingestion, the PostgreSQL raw loader where applicable, dbt, and QA. Incremental dbt facts reprocess a 30-day late-arrival window; older corrections require an approved full refresh.

Rollback changes `data/staging/v1/current.json` to the last verified immutable bundle, reloads its six tables transactionally, rebuilds dbt, and deploys the matching QA-passing analytical artifacts. Never combine code, warehouse state, or generated products from different releases.
