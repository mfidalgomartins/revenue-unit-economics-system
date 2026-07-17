# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Added

- Explicit synthetic and external pipeline profiles backed by one canonical
  dependency graph, with production runs unable to invoke the generator.
- Complete six-table ingestion, content-addressed immutable bundles, serialized
  atomic activation, manifest verification, and a transactional PostgreSQL raw
  loader with advisory locking and publication audit history.
- DuckDB/PostgreSQL API repository backends, query-backed readiness, and a
  schema-checked analytical-product cache.
- Week-clustered CR1 elasticity inference, assignment-balance diagnostics, and
  acquisition-window-aligned CAC for empirical payback.
- A non-overlapping scheduled-run wrapper, PostgreSQL CI smoke test, and tagged
  PDF output with semantic structure validation.
- Canonical raw-data contracts, fail-closed validation, domain and foreign-key
  checks, stronger final-output mutation tests, parseable PDF validation, and
  deterministic artifact-drift gates.
- Empirical 24-month payback evidence with recovered, right-censored, and
  insufficient-maturity states, including mature zero-transaction customers.
- Versioned HubSpot, Stripe, and Google Ads adapters with normalized contracts,
  bounded retries, incremental key merges, and source-version manifests.
- Tested dbt DuckDB/PostgreSQL warehouse with incremental facts, relationship
  checks, marts, dashboard exposure, and deterministic lineage publication.
- Randomized marketing incrementality, descriptive multi-touch attribution,
  randomized price elasticity, and bounded elasticity-based pricing decisions.
- Dependency-aware orchestration with SQLite attempt state, retries, stage SLAs,
  structured alerts, signed HTTPS webhooks, and a deployable UTC schedule.
- Authenticated FastAPI aggregate service with scoped API keys, Basic dashboard
  access, privacy suppression, security headers, request correlation, and an
  API-backed mode for the existing dashboard design.

### Changed

- Alert delivery is isolated per sink, resources close on every outcome, and
  transport failures cannot mask the persisted terminal pipeline state.
- Incremental ingestion uses per-table, pre-request boundaries and Stripe paid
  events so records cannot be skipped by cross-source timing or late payment.
- Causal API products enforce arm and model-sample privacy thresholds; snapshots
  suppress full-coverage channel economics for incompatible filtered slices.
- Stage subprocesses have hard process-group timeouts, and published operational
  lineage records the active source profile.
- Causal contribution outcomes may be signed while counts, prices, revenue,
  costs, and spend retain non-negative contracts.
- The live dashboard bootstrap carries only governed metadata rather than raw
  customer and transaction records; the visual implementation is unchanged.
- Cohort reporting now separates month-0 activation, signup activity,
  retained-from-month-0 activity, and revenue retention.
- Seed sensitivity evaluates alternate deterministic draws entirely in memory,
  leaving canonical raw and processed artifacts untouched.
- Scenario allocation uses LTV/CAC once as its score, publishes explicit
  allocation evidence, and enforces nonnegative bounded spend.
- Dashboard payload serialization escapes script boundaries; keyboard sorting,
  chart labels, and PDF navigation metadata are now validated.
- Documentation now covers ingestion, warehouse operation, causal claim
  boundaries, API deployment, privacy review, SLAs, and incident response.

### Fixed

- Removed the algebraic payback proxy, causal transaction-span language,
  annualized scenario wording, signed-residual QA defect, dead chart branch, and
  fail-open raw-validation exit behavior.
- Updated Pillow to 12.3.0 after the 2026 security advisories affecting 12.2.0.

## [2.3.1] - 2026-07-11

### Added

- Property-based tests (Hypothesis) for the metric registry: channel
  classification is total and monotone in both LTV/CAC and payback, NaN inputs
  always classify as undefined, and the risk score stays inside the registry's
  weight bounds for any finite input.

## [2.3.0] - 2026-07-10

### Added

- Reallocation stress lab in the dashboard: CAC and LTV response sliders apply
  the pipeline's stress formula to the embedded per-channel plan, with
  Best / Base / Worst presets that reproduce the report's stress table.
  Verified in-browser against the scenario engine's numbers and pinned by a
  payload parity test.

### Fixed

- Report prose said the stress multipliers apply "to the scaled channels";
  the engine applies them across every channel in the plan. The two captions
  now match the code.

## [2.2.0] - 2026-07-10

### Added

- Shared design tokens (`src/design/tokens.py`) imported by the chart pack and
  the PDF report, with a consistency test that pins the dashboard's CSS custom
  properties to the same values — a palette change now propagates everywhere
  or fails CI.
- SQL parity tests: the reference SQL in `sql/` runs with DuckDB in CI and
  must reproduce the pipeline's `customer_metrics` and `unit_economics`
  outputs.
- README product screenshots (light/dark via `<picture>`), a Mermaid pipeline
  diagram and a "from synthetic to production" section in
  `docs/ARCHITECTURE.md`, and a coverage badge.
- Golden regression assertions for the revenue decomposition and cohort
  retention sections.

### Changed

- The dashboard now embeds a columnar payload (integer day offsets, dimension
  indexes, customer row indexes) decoded by a small shim in the browser: the
  shipped HTML drops from 6.3 MB to 2.0 MB with identical rendering, KPIs,
  and filters.
- The dashboard template (~2,200 lines of HTML/CSS/JS) and the report
  stylesheet moved to asset files; the dashboard builder is now ~130 lines of
  tested logic at 100% coverage and no longer coverage-exempt.
- `PROJECT_ROOT` is resolved once in `src/paths.py` instead of in every module.
- The test suite runs warning-free (matplotlib's third-party pyparsing
  deprecation warnings are filtered with a documented rationale).

## [2.1.0] - 2026-07-10

### Added

- Redesigned the interactive dashboard around Apple's design language: SF Pro
  system typography with tabular (no longer monospace) numerals and tight
  display tracking, an Apple light/dark palette with system-blue accent and warm
  `#1d1d1f` ink, inset-grouped rounded cards with soft elevation, pill controls,
  and Apple motion/focus treatments. Light, dark, and mobile verified.
- Unified that design language across every visual surface: the 19-chart PNG
  pack, the analytical PDF report, and the GitHub Pages landing now share the
  same Apple palette (warm ink, system green/red/amber) so the README hero,
  report, dashboard, and site read as one product.
- Accessibility: improved positive KPI contrast and added semantic landmarks,
  labeled controls, chart alternatives, skip navigation, and reduced-motion
  support. Full WCAG conformance is not claimed.
- Dashboard now ships a favicon (inline SVG mark) and Open Graph / Twitter card
  metadata (hero chart as the share image) for a complete published-product feel.
- Consolidated quality tooling in `pyproject.toml`: ruff, mypy, pytest, and
  branch-coverage configuration.
- Unit and integration tests for synthetic data generation, the data catalog,
  raw profiling, the analytical section builders, metric-registry edge branches,
  and selected analytical and publication stage `run()` entry points; branch coverage raised to ~96% with an
  enforced 90% gate.
- Stricter typing: `disallow_untyped_defs`, `disallow_incomplete_defs`,
  `disallow_any_generics`, and `warn_return_any` enabled; all internal helpers
  annotated and generics parameterized.
- Security hardening: `SECURITY.md`, Dependabot for pip and GitHub Actions, a
  CodeQL static-analysis workflow, and `pip-audit` dependency scanning in CI.
- `CONTRIBUTING.md` and `make lint`/`type`/`audit`/`fmt`/`check` targets.

### Changed

- Pipeline stages now run as modules (`python -m src.<stage>`) from the project
  root, removing the per-module `sys.path` bootstrap hacks from six files.
- Added `docs/ARCHITECTURE.md` (stage contracts, on-disk data flow, determinism,
  extension points) and linked it from the README.
- Dashboard now honors `prefers-reduced-motion` (transitions, animations, and the
  chart-card hover-lift are neutralized for users who request reduced motion).
- CI now enforces lint, type-check, dependency audit, and the coverage gate in
  addition to the full pipeline run.
- Upgraded pytest to 9.0.3 to clear a known advisory in the test dependency.

### Fixed

- Dashboard no longer overflows horizontally on mobile: chart SVGs now use a
  `viewBox` so the drawing scales to the container, and chart cards get `min-width: 0`
  so they shrink within their grid track. Verified no overflow at 375/768/1280px.
- Removed dead assignments and unused imports flagged by ruff (behavior-preserving).

## [2.0.0] - 2026-06-11

### Added

- Nineteen-chart analytical pack and a reproducible 30-page PDF report.
- Five-seed scenario sensitivity analysis and stability visualization.
- Explicit metric contracts, data-quality checks, and publication QA.

### Changed

- Rebuilt the dashboard around growth quality, channel economics, and decision actions.
- Consolidated analytical tables under `outputs/tables/` and charts under `outputs/charts/`.
- Tightened README scope, methodology, limitations, and local run instructions.

### Removed

- Redundant chart packs, duplicate analytical tables, and obsolete governance scripts.

## [1.0.0] - 2026-04-02

### Added

- Initial deterministic revenue analytics pipeline, dashboard, tests, and release workflow.
