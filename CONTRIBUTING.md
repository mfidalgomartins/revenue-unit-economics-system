# Contributing

Thanks for taking a look. This project is a deterministic, self-contained
analytics pipeline: it generates synthetic data, computes unit economics, and
publishes a dashboard, chart pack, and report. Contributions should keep it
reproducible, well-tested, and honest about its synthetic scope.

## Development setup

```bash
make setup           # venv + dev dependencies + Chromium for the PDF/dashboard
source .venv/bin/activate
```

Python 3.12. No external services or credentials are required.

## The quality loop

All gates are configured in [`pyproject.toml`](pyproject.toml) and enforced in
CI. Run them locally before opening a pull request:

```bash
make lint     # ruff: lint src and tests
make type     # mypy: static type-check src
make audit    # pip-audit: scan pinned runtime and dev dependencies
make test     # pytest with branch coverage (gate: >= 90%)
make check    # lint + type + audit (static only, fast)
make qa       # full gate: check + pipeline run + test
```

`make fmt` applies `ruff format` if you want it, but formatting is not enforced
in CI — the existing hand-tuned layout in the chart and report builders is kept
intact.

### Conventions

- Type hints on public functions; `from __future__ import annotations` at the top.
- Keep analytical thresholds and policy in the metric registry
  (`src/governance/metric_registry.py`), not scattered across modules.
- New analytical logic needs unit tests. Pure helpers get direct tests; section
  builders are exercised against the committed deterministic data.
- Coverage must stay at or above 90%. Output renderers (the chart pack, the
  PDF report, final QA) are excluded from coverage because they are validated
  end-to-end by the pipeline run, not by unit tests — see the `omit` list in
  `pyproject.toml`. The dashboard builder is regular tested code.

## Changing analytical methodology or thresholds

Threshold changes ripple through analysis, dashboard classification, validation,
and published outputs. If you change one:

1. Update the metric registry.
2. Update affected tests and recommendation guardrails.
3. Re-run `make qa` and commit regenerated outputs intentionally.

## Pull requests

- Keep PRs focused and describe the analytical or engineering rationale.
- Ensure `make qa` is green.
- Update `CHANGELOG.md` for user-visible changes.

## Reporting security issues

See [SECURITY.md](SECURITY.md). Please do not open a public issue for an unfixed
vulnerability.
