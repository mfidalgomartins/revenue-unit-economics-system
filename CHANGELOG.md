# Changelog

All notable changes to this project are documented in this file.

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
- Accessibility: audited WCAG contrast across the palette and nudged the positive
  green to `#1a7f37` so KPI delta text clears AA (4.5:1) on white; every used
  text/background pair now meets AA in both themes. Audited semantics (heading
  hierarchy, `header`/`main` landmarks, labeled controls, chart text alternatives,
  skip link) and gave the filter bar a labeled `region` landmark.
- Dashboard now ships a favicon (inline SVG mark) and Open Graph / Twitter card
  metadata (hero chart as the share image) for a complete published-product feel.
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
