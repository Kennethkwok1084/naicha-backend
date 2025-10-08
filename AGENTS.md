# Repository Guidelines

## Project Structure & Module Organization
Core code lives under `app/`: routers (`app/api`), services (`app/services`), persistence (`app/models`), and support layers (`app/core`, `app/utils`, `app/ws`, `app/workers`). `migrations/` holds Alembic revisions, `infra/` captures deployment manifests, `tests/` mirrors the runtime layout, and `doc/api.md` must stay aligned with every endpoint.

## Build, Test, and Development Commands
Use `.env.example` to scaffold local configuration before any run. Start the stack with `docker compose up -d --build` for production parity. Run `make dev` for hot-reload Uvicorn once dependencies land. Quality gates: `make fmt` applies Black + isort, `make lint` runs Ruff/static checks, and `make test` executes the async pytest suite. Database flows rely on `make migrate` to generate Alembic revisions and `make updb` (alias of `alembic upgrade head`) to apply them.

## Coding Style & Naming Conventions
Python 3.11+, 4-space indentation, type hints, and FastAPI dependency injection are the defaults. Keep modules snake_case, classes PascalCase, Pydantic models suffixed with `Schema`, and database tables singular (`order_item`). Let `make fmt` handle formatting and `make lint` resolve import order or unused code. Route handlers stay skinny—push business logic into services and keep side effects idempotent.

## Testing Guidelines
Tests live under `tests/` and mirror the `app/` namespace. Name files `test_<module>.py` and prefer descriptive scenarios (`test_order_paid_state_transition`). Every API change must ship unit coverage plus concurrency, permission, and idempotency checks where relevant. Target ≥70% service-layer coverage and note load or latency evidence for critical paths in PRs. Run `make test` before pushing and mock external systems (payment, printing, messaging).

## Commit & Pull Request Guidelines
Follow Conventional Commits (`feat: add loyalty accrual audit`) so CI parsing and change logs stay consistent. Each PR should link the tracked issue or milestone and describe the user-facing impact. Update `doc/api.md` whenever an endpoint's request, response, or limits change; missing documentation blocks merge. Include `make lint`/`make test` results, migration rationale with rollback notes, and highlight any feature flag expectations.

## Configuration & Security Notes
Never commit real secrets—copy `.env.example`, fill in values locally, and store production secrets in the orchestrator’s vault. Feature toggles (`MULTI_CATEGORY_ENABLED`, `RESERVATION_ENABLED`, etc.) must default safely for cloud deployments. When altering observability or networking, document port changes and Prometheus toggles so K3s manifests stay synced.

## Rules
Always reposed in Chinese/中文, as per the original document.
使用“如无必要不增加实体”原则，使用最小化、最优解、最低性能开销原则