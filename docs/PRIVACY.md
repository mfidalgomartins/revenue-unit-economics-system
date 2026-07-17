# Privacy review

## Publication classes

| Surface | Data class | Policy |
|---|---|---|
| Static portfolio dashboard | deterministic synthetic records | Public; clearly labeled synthetic |
| Authenticated dashboard API | thresholded aggregates | Internal aggregate; minimum cell size 10 |
| Channel and causal endpoints | channel, experiment, and product aggregates | Internal aggregate; authenticated and scoped |
| Staging customer contract | pseudonymous ID plus governed dimensions | Restricted; no direct contact or payment fields |
| Runtime operations store | run IDs, stage names, status, timing, error type | Internal operational; no analytical rows or secrets |

## Data minimization

The real-source CRM adapter retains only pseudonymous customer ID, signup date, segment, region, and acquisition channel. Billing normalization keeps economic invoice fields and a governed CRM identifier. Advertising normalization keeps date, channel, and spend. Raw vendor responses, names, email addresses, phone numbers, payment instruments, IP addresses, user agents, ad creative, and free-text properties are not published.

## Aggregate API controls

- Filtering is executed server-side against read-only dbt facts and dimensions.
- The browser receives monthly series, thresholded dimension tables, channel aggregates, cohort medians, and quantile histogram bins—not customer, transaction, touchpoint, or invoice identifiers.
- Requested slices with fewer than 10 active customers return a generic unavailable response.
- Dimension rows, experiment arms, and model samples below 10 are omitted. A pricing recommendation is exposed only when its product-level elasticity evidence clears the threshold.
- Full-coverage unit economics are suppressed when date, segment, region, or product filters would create a misleading mixed-scope response.
- Basic and API-key responses use `Cache-Control: no-store`.
- Authentication failures do not reveal whether a principal ID exists.

Minimum cell size is a disclosure control, not anonymization proof. A production privacy assessment must consider differencing attacks, repeated queries, rare dimension combinations, external data linkage, retention, jurisdiction, data-subject rights, and the organization's lawful basis.

## Deployment checklist

1. Replace source identifiers with stable pseudonyms before staging when the analytical join does not require vendor IDs.
2. Restrict staging, warehouse, and runtime-state access by service account and environment.
3. Apply encryption in transit and at rest through the deployment platform.
4. Set retention and deletion schedules for staging tables and operational logs.
5. Put shared pre-authentication rate limiting and query monitoring in front of multi-replica APIs.
6. Review every new dimension or endpoint for small-cell and differencing risk.
7. Run a jurisdiction-specific privacy and security review before using personal data.
