PYTHON ?= python
POETRY ?= poetry
UVICORN ?= uvicorn

.PHONY: install install-dev fmt lint test dev migrate updb compose-up compose-down coverage contract-test worker perf-locust perf-ws diag-payment seed-data seed-clean seed-dev seed-perf pre-deploy validate-prod export-openapi

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
	celery -A app.workers.celery_app:celery_app worker -Q analytics,default,print_jobs --loglevel=info

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

# ============================================
# 上线验证相关命令
# ============================================

export-openapi:
	@echo "=========================================="
	@echo "导出 OpenAPI 文档"
	@echo "=========================================="
	@$(PYTHON) -c "import json; from app.main import app; f = open('naicha-openapi.json', 'w', encoding='utf-8'); json.dump(app.openapi(), f, indent=2, ensure_ascii=False); f.close(); print('✅ OpenAPI 文档已导出: naicha-openapi.json')"
	@echo ""
	@echo "📝 下一步: 将此文件导入到 Apifox 或 Postman"
	@echo "   详见: doc/apifox-quick-start.md"

validate-prod:
	@echo "=========================================="
	@echo "生产环境配置验证"
	@echo "=========================================="
	@if [ -z "$$PROD_POD_NAME" ]; then \
		echo "❌ 请设置 PROD_POD_NAME 环境变量"; \
		echo "   示例: export PROD_POD_NAME=naicha-backend-xxx"; \
		exit 1; \
	fi
	@kubectl exec -n production $$PROD_POD_NAME -- bash -c '\
echo "=== 限流配置 ==="; \
echo "RATE_LIMIT_DEFAULT_LIMITS: $$RATE_LIMIT_DEFAULT_LIMITS"; \
echo "PERF_DISABLE_HTTP_OVERHEADS: $${PERF_DISABLE_HTTP_OVERHEADS:-未设置(正确)}"; \
echo ""; \
echo "=== JWT 配置 ==="; \
echo "JWT_EXPIRE_MINUTES: $$JWT_EXPIRE_MINUTES"; \
echo ""; \
echo "=== 数据库配置 ==="; \
echo "DATABASE_POOL_SIZE: $$DATABASE_POOL_SIZE"; \
echo "DATABASE_MAX_OVERFLOW: $$DATABASE_MAX_OVERFLOW"'
	@echo ""
	@echo "=== Redis 连通性 ==="
	@redis-cli -h 172.21.48.1 PING && echo "✅ Redis 可达" || echo "❌ Redis 不可达"
	@echo ""
	@echo "=== 数据库迁移状态 ==="
	@kubectl exec -n production $$PROD_POD_NAME -- alembic current
	@echo ""
	@echo "✅ 配置验证完成！详细清单见: doc/production-readiness-checklist.md"

pre-deploy:
	@echo "=========================================="
	@echo "上线前完整检查"
	@echo "=========================================="
	@echo ""
	@echo "📋 执行检查清单..."
	@echo ""
	@echo "1️⃣  代码质量检查"
	@$(MAKE) fmt
	@$(MAKE) lint
	@echo "✅ 代码质量检查通过"
	@echo ""
	@echo "2️⃣  单元测试"
	@$(MAKE) test
	@echo "✅ 单元测试通过"
	@echo ""
	@echo "3️⃣  测试覆盖率"
	@$(MAKE) coverage
	@echo "✅ 测试覆盖率检查完成"
	@echo ""
	@echo "4️⃣  导出 OpenAPI 文档"
	@$(MAKE) export-openapi
	@echo ""
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "✅ 本地验证通过！"
	@echo ""
	@echo "📋 下一步行动清单:"
	@echo "   1. 将 naicha-openapi.json 导入 Apifox 进行 API 测试"
	@echo "   2. 部署到 Staging 环境并执行集成测试"
	@echo "   3. 执行 150 并发压测: cd infra/perf && ./run_150_concurrent_test.sh"
	@echo "   4. 执行 Redis 故障演练: cd infra/perf && ./redis_fault_drill.sh"
	@echo "   5. 查看生产配置清单: doc/production-readiness-checklist.md"
	@echo ""
	@echo "📖 完整上线指南: doc/pre-production-validation-guide.md"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
