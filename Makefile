PYTHON ?= python3
VENV ?= .venv

.PHONY: setup run test qa clean

setup:
	$(PYTHON) -m venv $(VENV)
	. $(VENV)/bin/activate && pip install --upgrade pip && pip install -r requirements-dev.txt
	. $(VENV)/bin/activate && python -m playwright install chromium

run:
	. $(VENV)/bin/activate && python src/run_pipeline.py

test:
	. $(VENV)/bin/activate && pytest -q

qa: run test

clean:
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	rm -rf .pytest_cache htmlcov .coverage .cache
