.PHONY: dev dev-backend dev-frontend migrate lint test build clean

# ─── Local Development ────────────────────────────────────────────────────────
dev:
	docker compose up -d

dev-backend:
	cd backend && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend:
	cd frontend && pnpm dev

# ─── Database ─────────────────────────────────────────────────────────────────
migrate:
	cd backend && uv run alembic upgrade head

migrate-create:
	cd backend && uv run alembic revision --autogenerate -m "$(msg)"

migrate-down:
	cd backend && uv run alembic downgrade -1

# ─── Code Quality ─────────────────────────────────────────────────────────────
lint:
	cd backend && uv run ruff check . && uv run mypy app/
	cd frontend && pnpm lint

format:
	cd backend && uv run ruff format .

# ─── Tests ────────────────────────────────────────────────────────────────────
test:
	cd backend && uv run pytest tests/ -v

test-coverage:
	cd backend && uv run pytest tests/ --cov=app --cov-report=html

# ─── Build ────────────────────────────────────────────────────────────────────
build:
	docker compose build

# ─── Infra ────────────────────────────────────────────────────────────────────
tf-init:
	cd infra/terraform && terraform init

tf-plan:
	cd infra/terraform && terraform plan

tf-apply:
	cd infra/terraform && terraform apply

# ─── Cleanup ──────────────────────────────────────────────────────────────────
clean:
	docker compose down -v
	find backend -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find backend -name "*.pyc" -delete 2>/dev/null || true
