PYTHON ?= python
POETRY ?= poetry
UVICORN ?= uvicorn

.PHONY: install install-dev fmt lint test dev migrate updb compose-up compose-down coverage contract-test worker

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

worker:
	celery -A app.workers.celery_app:celery_app worker --loglevel=info

migrate:
	alembic revision --autogenerate -m "describe changes"

updb:
	alembic upgrade head

compose-up:
	docker compose up -d --build

compose-down:
	docker compose down

contract-test:
	@set -euo pipefail; \
	STATUS=0; \
	DATABASE_URL=sqlite+aiosqlite:///:memory: $(PYTHON) -m uvicorn app.main:app --host 127.0.0.1 --port 8123 --log-level warning & \
	SERVER_PID=$$!; \
	sleep 2; \
	DATABASE_URL=sqlite+aiosqlite:///:memory: $(PYTHON) -m schemathesis.cli run http://127.0.0.1:8123/openapi.json --url http://127.0.0.1:8123 --workers=1 --max-examples=5 --phases=examples || STATUS=$$?; \
	kill $$SERVER_PID; \
	wait $$SERVER_PID 2>/dev/null || true; \
	exit $$STATUS
