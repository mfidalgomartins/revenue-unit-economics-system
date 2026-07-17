PYTHON ?= python3.12
VENV ?= .venv
ACTIVATE = . $(VENV)/bin/activate

.PHONY: setup run orchestrate ingest load-postgres warehouse api api-key-hash dashboard report test lint fmt-check type deps audit fmt check qa clean

API_HOST ?= 127.0.0.1
API_PORT ?= 8000

setup:
	$(PYTHON) -m venv $(VENV)
	$(ACTIVATE) && pip install -r requirements-dev.txt
	$(ACTIVATE) && python -m playwright install chromium

run:
	$(ACTIVATE) && python -m src.run_pipeline

orchestrate:
	$(ACTIVATE) && python -m src.operations.orchestrator

ingest:
	$(ACTIVATE) && python -m src.ingestion.run_ingestion

load-postgres:
	$(ACTIVATE) && python -m src.ingestion.load_postgres

warehouse:
	$(ACTIVATE) && python -m src.warehouse.run_dbt

api:
	$(ACTIVATE) && uvicorn src.api.app:create_app --factory --host $(API_HOST) --port $(API_PORT)

api-key-hash:
	$(ACTIVATE) && python -m src.api.hash_key

# Rebuild a single publication surface against the committed tables.
dashboard:
	$(ACTIVATE) && python -m src.dashboard_builder.build_dashboard_assets

report:
	$(ACTIVATE) && python -m src.governance.build_analytical_report

test:
	$(ACTIVATE) && pytest

lint:
	$(ACTIVATE) && ruff check src tests

fmt-check:
	$(ACTIVATE) && ruff format --check src tests

type:
	$(ACTIVATE) && mypy

deps:
	$(ACTIVATE) && pip check

audit:
	$(ACTIVATE) && pip-audit -r requirements-dev.txt

fmt:
	$(ACTIVATE) && ruff format src tests

# Static gates only. No pipeline run required.
check: lint fmt-check type deps audit

# Full gate: static checks, pipeline run, and tests with the coverage gate.
qa: check run test

clean:
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	rm -rf .pytest_cache htmlcov .coverage .cache .ruff_cache .mypy_cache warehouse/target warehouse/logs outputs/operations
