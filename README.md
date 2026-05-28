# Revenue Analytics & Unit Economics

A self-contained analytics pipeline that answers one question: **is growth sustainable, or is it expensive?**

Top-line growth can mask weak acquisition efficiency, fragile retention, or margin erosion. This project takes synthetic but realistic commercial data and produces governed metrics, cohort and channel diagnostics, scenario simulations, and an interactive dashboard — all reproducible from a single command.

**Live dashboard:** https://mfidalgomartins.github.io/revenue-unit-economics-system/

## What it answers
- Which acquisition channels to scale or cut, based on LTV/CAC and payback.
- Which segments, products, or regions are diluting contribution margin.
- Which cohorts show early-life retention decay worth intervening on.
- How to reallocate spend under profitability guardrails — and what the best/worst-case envelope looks like.

## Pipeline
```
data generation → raw validation → profiling → feature engineering →
core analysis → scenario engine → visuals + dashboard →
final QA → governance artifacts
```
Every stage writes deterministic outputs under `outputs/` and `data/processed/`. A metric registry (`src/governance/metric_registry.py`) defines LTV, CAC, payback and efficiency thresholds in one place; analysis, dashboard, and validation all read from it.

## Run
```bash
make setup    # create venv and install dev requirements
make qa       # run the full pipeline and the test suite
```
Or, without `make`:
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python src/run_pipeline.py && pytest -q
```
Python 3.12. No external services or credentials required.

## Layout
```
src/         pipeline stages (one package per stage)
data/        raw and processed CSVs (raw is generated, deterministic seed)
sql/         reference SQL for the core feature tables
outputs/     charts, tables, reports, and the dashboard
tests/       unit tests + metric contract tests + dashboard payload tests
```

## Key outputs
- `outputs/dashboard/growth-quality-dashboard.html` — interactive dashboard with filters, drill-downs, and embedded data.
- `outputs/reports/decision_brief.md` — executive summary with recommendations and scenario envelope.
- `outputs/tables/scenario_reallocation_plan.csv` — per-channel reallocation under the chosen policy.
- `outputs/reports/pre_delivery_validation_report.md` — final QA gate before publishing.
- `outputs/reports/metric_governance_registry.md` — metric definitions and thresholds in human-readable form.

## Limitations
- Data is synthetic. The pipeline demonstrates method and rigor, not a real market.
- LTV is observed contribution margin per customer over the available window — not a forward forecast.
- CAC uses period-level spend over customers acquired in the channel; no multi-touch attribution.
- Scenarios apply bounded CAC/LTV elasticities under spend changes; they are policy simulations, not predictions.

## Stack
Python 3.12, pandas, NumPy, matplotlib, vanilla JS/HTML/CSS for the dashboard, GitHub Actions for CI and tagged releases.

## License
MIT — see [LICENSE](LICENSE).
