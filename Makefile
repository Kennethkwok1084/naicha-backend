PYTHON ?= python
POETRY ?= poetry
UVICORN ?= uvicorn

.PHONY: install install-dev fmt lint test dev migrate updb compose-up compose-down coverage contract-test worker perf-locust perf-ws diag-payment seed-data seed-clean seed-dev seed-perf

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

diag-payment:
	@echo "=========================================="
	@echo "支付回调诊断工具"
	@echo "=========================================="
	@if [ -z "$$PERF_SECRET_KEY" ]; then echo "⚠️  警告: PERF_SECRET_KEY 未设置"; fi
	@$(PYTHON) scripts/test_payment_callback.py

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

perf-locust:
	@if [ -z "$$PERF_BASE_URL" ]; then echo "请设置 PERF_BASE_URL 环境变量"; exit 1; fi
	locust -f infra/perf/locustfile.py --headless --users 100 --spawn-rate 20 --run-time 30s

perf-ws:
	@if [ -z "$$PERF_ADMIN_TOKEN" ]; then echo "请设置 PERF_ADMIN_TOKEN 环境变量"; exit 1; fi
	$(PYTHON) infra/perf/ws_runner.py --connections 50 --duration 60

perf-baseline:
	@echo "=========================================="
	@echo "执行 Week1 完整压测基线"
	@echo "=========================================="
	@if [ -z "$$PERF_BASE_URL" ]; then echo "❌ 请设置 PERF_BASE_URL 环境变量"; exit 1; fi
	@bash infra/perf/run_baseline.sh
	@echo ""
	@echo "📊 开始解析结果并更新文档..."
	@$(PYTHON) infra/perf/parse_results.py --input ./perf_results --baseline ./doc/perf-baseline.md
	@echo ""
	@echo "✅ 完成！查看报告: open perf_results/locust_*.html"

seed-data:
	@echo "=========================================="
	@echo "创建完整测试数据"
	@echo "=========================================="
	@$(PYTHON) scripts/seed_test_data.py
	@echo ""
	@echo "✅ 测试数据创建完成！"

seed-clean:
	@echo "=========================================="
	@echo "清空并重新创建测试数据"
	@echo "=========================================="
	@$(PYTHON) scripts/seed_test_data.py --clean
	@echo ""
	@echo "✅ 测试数据已重置！"

seed-dev:
	@echo "=========================================="
	@echo "创建开发环境管理员账号"
	@echo "=========================================="
	@if [ -z "$$NAICHA_DEV_ADMIN_HASH" ]; then \
		echo "❌ 请设置 NAICHA_DEV_ADMIN_HASH 环境变量"; \
		echo "   示例: export NAICHA_DEV_ADMIN_HASH='$$2b$$12$$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYvZt5UbQfq'"; \
		exit 1; \
	fi
	@$(PYTHON) scripts/seed_dev.py
	@echo ""
	@echo "✅ 管理员账号创建完成！"

seed-perf:
	@echo "=========================================="
	@echo "创建性能测试数据"
	@echo "=========================================="
	@$(PYTHON) scripts/seed_perf_data.py
	@echo ""
	@echo "✅ 性能测试数据创建完成！"
