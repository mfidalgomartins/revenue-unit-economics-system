# Real-source ingestion

The external profile normalizes six inputs into contract version `1.0.0`. Source payloads are validated in memory and are not retained. Publication succeeds only when the complete bundle passes schema, key, domain, finite-value, and cross-table customer checks.

## Source mappings

| Adapter | Source | Published table | Required source fields |
|---|---|---|---|
| HubSpot CRM | objects API v3 | `customers.csv` | contact ID, creation date, governed segment, region, and acquisition-channel properties |
| Stripe Billing | version-pinned invoices and events APIs | `transactions.csv` | paid invoice ID/date/amount plus governed customer ID, direct cost, and product metadata |
| Google Ads | search-stream API, default v24 | `marketing_spend.csv` | date, campaign ID, and cost micros; every campaign ID requires an explicit channel mapping |
| Governed CSV drop | experiment/activation exports | `marketing_touchpoints.csv` | touch ID, customer ID, date, channel, order, conversion flag |
| Governed CSV drop | randomized holdout export | `marketing_experiments.csv` | experiment/customer IDs, assignment, window, pre-period and observed outcomes |
| Governed CSV drop | randomized pricing export | `pricing_interventions.csv` | intervention cell, week, product, region, assignment, price, units, revenue, contribution |

The normalized customer table excludes names, email addresses, phone numbers, payment methods, ad copy, and free-text CRM properties.

## Configuration

Credentials and source settings come only from environment variables:

```text
HUBSPOT_ACCESS_TOKEN
HUBSPOT_SEGMENT_PROPERTY
HUBSPOT_REGION_PROPERTY
HUBSPOT_CHANNEL_PROPERTY

STRIPE_SECRET_KEY
STRIPE_API_VERSION
STRIPE_CUSTOMER_ID_METADATA_KEY
STRIPE_DIRECT_COST_METADATA_KEY
STRIPE_PRODUCT_METADATA_KEY

GOOGLE_ADS_ACCESS_TOKEN
GOOGLE_ADS_DEVELOPER_TOKEN
GOOGLE_ADS_CUSTOMER_ID
GOOGLE_ADS_LOGIN_CUSTOMER_ID
GOOGLE_ADS_API_VERSION
GOOGLE_ADS_CHANNEL_MAP

GOVERNED_INPUT_DIR
INGESTION_START_DATE
INGESTION_END_DATE
```

`GOOGLE_ADS_CHANNEL_MAP` is a JSON object from campaign ID to `paid_search`, `social_ads`, `referral`, `organic`, `partners`, or `email`. `GOVERNED_INPUT_DIR` must contain the three governed CSV files in the table above. Initial loads require `INGESTION_START_DATE`; later ad-spend loads use that table's active manifest timestamp unless a start date is supplied.

## Publish and run

```bash
make ingest
PIPELINE_PROFILE=external RAW_DATA_DIR=data/staging make run
```

`make ingest` writes an immutable snapshot under `data/staging/v1/bundles/<bundle_id>/`. The content-derived bundle ID, manifest row counts, and SHA-256 file digests are verified before use. `data/staging/v1/current.json` is replaced atomically only after all six tables are durable. A process lock serializes merge and activation, so readers see either the previous complete bundle or the new complete bundle.

The external pipeline refuses plain CSV directories without a verified bundle manifest. The synthetic profile rejects `RAW_DATA_DIR` entirely, so a missing profile variable cannot redirect generated data into the production source boundary.

Incremental cursors are tracked per table rather than as one global watermark. Every run records the boundary captured before source requests begin, deliberately overlapping the next idempotent merge so records created during extraction cannot fall between cursors. Stripe increments consume `invoice.paid` events, which captures invoices created earlier but paid after the previous boundary. Empty deltas are valid only when a prior complete table exists. Backfills use an explicit earlier date and the same primary-key merge. Source-side deletions require an approved full snapshot or a future tombstone contract; absence from an incremental response is not interpreted as deletion.

## PostgreSQL production load

Load the verified active bundle before running dbt in production:

```bash
export RAW_DATA_DIR=data/staging
export INGESTION_POSTGRES_DSN='postgresql://...'
export WAREHOUSE_RAW_SCHEMA=raw
make load-postgres

export DBT_TARGET=prod
make warehouse
```

The loader takes a PostgreSQL advisory transaction lock, copies all six tables into candidate relations, verifies row counts, then replaces the contents of the stable raw relations and records the bundle ID in `raw._ingestion_publications`. Any failure rolls back the complete load; dbt never sees a mixed bundle.

## Failure behavior

- HTTP retries are bounded and limited to transport failures, throttling, and transient server statuses.
- Error messages contain method, route, status, and error type—not credentials or response bodies.
- Unknown channel mappings, missing Stripe metadata, missing governed files, blank identifiers, orphan customers, schema drift, incompatible versions, and non-finite values block publication. Counts, prices, revenue, costs, and spend must be non-negative; contribution outcomes and contribution margin may be signed.
- A failed write or pointer replacement preserves the previous active snapshot.
- Vendor-version upgrades require adapter regression tests and a contract compatibility review.
