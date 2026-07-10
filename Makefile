PYTHON ?= python3
VENV ?= .venv
ACTIVATE = . $(VENV)/bin/activate

.PHONY: setup run dashboard report test lint type audit fmt check qa clean

setup:
	$(PYTHON) -m venv $(VENV)
	$(ACTIVATE) && pip install --upgrade pip && pip install -r requirements-dev.txt
	$(ACTIVATE) && python -m playwright install chromium

run:
	$(ACTIVATE) && python -m src.run_pipeline

# Rebuild a single publication surface against the committed tables.
dashboard:
	$(ACTIVATE) && python -m src.dashboard_builder.build_dashboard_assets

report:
	$(ACTIVATE) && python -m src.governance.build_analytical_report

test:
	$(ACTIVATE) && pytest

lint:
	$(ACTIVATE) && ruff check src tests

type:
	$(ACTIVATE) && mypy

audit:
	$(ACTIVATE) && pip-audit -r requirements.txt && pip-audit -r requirements-dev.txt

fmt:
	$(ACTIVATE) && ruff format src tests

# Static gates only: lint + type + audit. No pipeline run required.
check: lint type audit

# Full gate: static checks, pipeline run, and tests with the coverage gate.
qa: check run test

clean:
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	rm -rf .pytest_cache htmlcov .coverage .cache .ruff_cache .mypy_cache
