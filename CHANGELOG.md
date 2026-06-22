# Changelog

All notable changes to this project are documented in this file.

## [2.1.0] - 2026-06-18

### Added

- Redesigned the interactive dashboard around Apple's design language: SF Pro
  system typography with tabular (no longer monospace) numerals and tight
  display tracking, an Apple light/dark palette with system-blue accent and warm
  `#1d1d1f` ink, inset-grouped rounded cards with soft elevation, pill controls,
  and Apple motion/focus treatments. Light, dark, and mobile verified.
- Consolidated quality tooling in `pyproject.toml`: ruff, mypy, pytest, and
  branch-coverage configuration.
- Unit and integration tests for synthetic data generation, the data catalog,
  raw profiling, the analytical section builders, metric-registry edge branches,
  and every stage `run()` entry point; branch coverage raised to ~96% with an
  enforced 90% gate.
- Stricter typing: `disallow_untyped_defs`, `disallow_incomplete_defs`,
  `disallow_any_generics`, and `warn_return_any` enabled; all internal helpers
  annotated and generics parameterized.
- Security hardening: `SECURITY.md`, Dependabot for pip and GitHub Actions, a
  CodeQL static-analysis workflow, and `pip-audit` dependency scanning in CI.
- `CONTRIBUTING.md` and `make lint`/`type`/`audit`/`fmt`/`check` targets.

### Changed

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
