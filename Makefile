PYTHON ?= python
POETRY ?= poetry
UVICORN ?= uvicorn

.PHONY: install install-dev fmt lint test dev migrate updb compose-up compose-down coverage

install:
	$(PYTHON) -m pip install -r requirements.txt

install-dev:
	$(PYTHON) -m pip install -r requirements-dev.txt

fmt:
	$(PYTHON) -m black app tests
	$(PYTHON) -m isort app tests

lint:
	$(PYTHON) -m ruff check app tests

test:
	$(PYTHON) -m pytest

coverage:
	$(PYTHON) -m coverage run -m pytest
	$(PYTHON) -m coverage report

dev:
	$(UVICORN) app.main:app --reload --host 0.0.0.0 --port 8000

migrate:
	alembic revision --autogenerate -m "describe changes"

updb:
	alembic upgrade head

compose-up:
	docker compose up -d --build

compose-down:
	docker compose down
