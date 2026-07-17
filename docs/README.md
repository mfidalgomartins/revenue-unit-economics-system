# Documentation

Design and operating detail that sits behind the top-level [README](../README.md). Start there for the business case, the dashboard, and the report; come here for how the system is built and run.

| Doc | Read this for |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | The two operating modes (synthetic case vs. real-source production path), stage contracts, source boundaries, the warehouse, dashboard/API relationship, determinism guarantees, and deployment boundaries |
| [INGESTION.md](INGESTION.md) | The real-source ingestion contract: normalized six-table schema, versioned vendor adapters, atomic bundle publication, and the transactional PostgreSQL loader |
| [CAUSAL_METHODS.md](CAUSAL_METHODS.md) | How the system separates causal claims (randomized incrementality, price elasticity) from descriptive allocation (multi-touch attribution), and where each is and isn't valid |
| [API.md](API.md) | The authenticated FastAPI aggregate service: scoped API keys, privacy-thresholded responses, and how it serves the same dashboard surface in live mode |
| [PRIVACY.md](PRIVACY.md) | Publication classes, suppression rules, and what the API will and won't return at the aggregate level |
| [OPERATIONS.md](OPERATIONS.md) | Pipeline profiles, the orchestrator's retry/SLA/alerting behavior, the deployable schedule, and the incident runbook |

## Product screenshots

`images/dashboard-light.jpg` and `images/dashboard-dark.jpg` are the dashboard screenshots used in the root README; regenerate them from the live dashboard if the visual design changes so the two stay in sync.
