# Architecture

This document explains how the system is put together: the pipeline shape, the
contract between stages, and the design decisions that keep it reproducible. For
*what* it analyzes and how to run it, see the [README](../README.md).

## Design in one sentence

A linear, deterministic batch pipeline of independent stages that communicate
only through files on disk, with all analytical policy centralized in one metric
registry.

## Stage pipeline

`src/run_pipeline.py` runs twelve stages in a fixed order. Each stage is a
self-contained module with a `main()` entry point; the orchestrator invokes them
as subprocesses so a failure in one stage stops the run with a clear boundary.

```
data generation        src/data_generation/        → data/raw/*.csv
raw validation         src/validation/             → outputs/tables/raw_validation_summary.csv
profiling              src/data_profiling/         → outputs/tables/data_profile_summary.csv, data_quality_issues.csv
feature engineering    src/feature_engineering/    → data/processed/{customer_metrics,cohort_table,unit_economics}.csv
core analysis          src/analysis/               → outputs/tables/*.csv (monthly health, decomposition, cohorts, …)
scenario engine        src/scenario_engine/        → outputs/tables/scenario_*.csv
seed sensitivity       src/scenario_engine/        → outputs/tables/scenario_seed_sensitivity*.csv
chart pack             src/visualization/          → outputs/charts/*.png
dashboard              src/dashboard_builder/      → outputs/dashboard/growth-quality-dashboard.html
supporting docs        src/governance/             → outputs/reports/{metric_registry,decision_brief}.md, data_catalog.csv
analytical PDF         src/governance/             → outputs/reports/revenue_unit_economics_report.pdf
final QA gate          src/validation/             → outputs/reports/qa_report.md, outputs/tables/qa_checks.csv
```

## The on-disk contract

Stages never import each other's runtime state; they read and write CSV/HTML/PDF
artifacts at well-known paths. This is deliberate:

- **Inspectable** — every intermediate result is a file you can open and diff.
- **Resumable / debuggable** — a stage can be rerun in isolation against the
  artifacts already on disk.
- **Decoupled** — a stage only needs to know the *schema* of the files it reads,
  not the internals of the stage that produced them.

Directory roles:

| Path | Role | Producer |
|------|------|----------|
| `data/raw/` | synthetic source tables | data generation |
| `data/processed/` | customer-level feature tables | feature engineering |
| `outputs/tables/` | analytical result tables | analysis, scenarios, profiling, QA |
| `outputs/charts/` | publication PNG chart pack | visualization |
| `outputs/dashboard/` | self-contained interactive HTML | dashboard builder |
| `outputs/reports/` | decision brief, metric registry, QA report, PDF | governance, validation |

The data catalog (`src/governance/data_catalog.py`) documents the columns of these
tables and is itself published as `outputs/tables/data_catalog.csv`.

## Single source of truth: the metric registry

`src/governance/metric_registry.py` holds every unit-economics threshold and
risk-scoring default (LTV/CAC targets, payback bounds, margin floor, scoring
weights) plus the canonical `classify_channel_efficiency` and
`channel_priority_score` functions. Analysis, the dashboard, and validation all
import from it — a threshold is defined once and consumed everywhere, so the
published numbers, the dashboard's color coding, and the QA checks cannot drift
apart. Changing policy means editing this one module (and its tests).

## Determinism

The pipeline is reproducible by construction:

- Synthetic generation is seeded (`SYNTHETIC_SEED`, default 42); the same seed
  yields byte-identical raw data.
- Every downstream stage is a pure function of its input files.
- Seed sensitivity reruns the *same* generating process across five deterministic
  seeds to measure scenario-direction stability — it tests robustness, not
  external validity.

The only intentional non-determinism is the PDF's byte size (the headless-browser
PDF encoder is not byte-stable); all *content* is deterministic, and the final QA
gate asserts the substantive invariants rather than file bytes.

## Testing and coverage strategy

- **Pure logic** (metric registry, feature math, analysis section builders, data
  generation invariants) is unit-tested directly.
- **Stage `run()` entry points** are exercised against the committed data with
  their output directory redirected to a temp path, so orchestration and writers
  are covered without mutating tracked artifacts.
- **Output renderers** (chart pack, dashboard HTML, PDF, final QA) are excluded
  from coverage (`tool.coverage.run.omit` in `pyproject.toml`) because their value
  is the produced artifact, validated end to end by the pipeline run in CI rather
  than by branch-level unit tests.

The enforced branch-coverage gate is 90% (currently ~96%).

## Quality gates

Configured in `pyproject.toml` and enforced in CI (`.github/workflows/`):
ruff (lint), mypy (typed, with a strict subset — `disallow_untyped_defs`,
`disallow_any_generics`, `warn_return_any`; matplotlib's untyped call API is
intentionally not fought), pytest + branch coverage, and `pip-audit`. CodeQL and
Dependabot run on schedule.

## Extending the system

- **New analytical question** → add a `compute_*` function in `src/analysis/`,
  write it to a new `outputs/tables/` CSV, add a chart in `src/visualization/`,
  and surface it in the dashboard/report. Add a unit test for the new function.
- **New policy threshold** → add it to the metric registry, update dependent
  tests and any recommendation guardrails, then rerun `make qa`.
- **New pipeline stage** → add a module with a `main()`, insert it into the
  `STEPS` list in `src/run_pipeline.py` at the right point in the dependency order.

## Frontend (dashboard)

The dashboard is a single self-contained HTML file generated by
`src/dashboard_builder/build_dashboard_assets.py`: embedded JSON payload, vanilla
JS for filtering and hand-rolled SVG charts, and a CSS design system with light/
dark themes (Apple-style typography and surfaces), a print stylesheet, and a
reduced-motion media query. Charts use a `viewBox` so they scale responsively
without horizontal overflow on small screens.
