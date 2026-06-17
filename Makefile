.PHONY: help install dev test lint format migrate upgrade docker-up docker-down clean

# ── Default ───────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "PR Review Agent — available commands:"
	@echo ""
	@echo "  make install      Install dependencies into virtualenv"
	@echo "  make dev          Start API server in hot-reload mode"
	@echo "  make worker       Start Dramatiq worker"
	@echo "  make test         Run all tests"
	@echo "  make lint         Run ruff linter"
	@echo "  make format       Auto-format code with ruff"
	@echo "  make migrate      Run pending Alembic migrations"
	@echo "  make migration    Create a new migration (MSG=<description>)"
	@echo "  make docker-up    Start all services with docker-compose"
	@echo "  make docker-down  Stop all services"
	@echo "  make clean        Remove .pyc, __pycache__, .pytest_cache"
	@echo ""

# ── Setup ─────────────────────────────────────────────────────────────────────
install:
	python3 -m venv venv
	./venv/bin/pip install --upgrade pip
	./venv/bin/pip install -r requirements.txt
	./venv/bin/pip install pytest pytest-asyncio httpx ruff

# ── Local dev ─────────────────────────────────────────────────────────────────
dev:
	uvicorn server:app --host 0.0.0.0 --port 8000 --reload

worker:
	dramatiq workers.pr_worker --processes 2 --threads 4 --watch .

# ── Testing ───────────────────────────────────────────────────────────────────
test:
	pytest tests/ -v --tb=short

test-cov:
	pytest tests/ -v --tb=short --cov=. --cov-report=term-missing --cov-report=html

# ── Code quality ──────────────────────────────────────────────────────────────
lint:
	ruff check .

format:
	ruff format .
	ruff check --fix .

# ── Database ──────────────────────────────────────────────────────────────────
migrate:
	alembic upgrade head

migration:
	@test -n "$(MSG)" || (echo "Usage: make migration MSG='describe the change'" && exit 1)
	alembic revision --autogenerate -m "$(MSG)"

downgrade:
	alembic downgrade -1

db-history:
	alembic history --verbose

# ── Docker ────────────────────────────────────────────────────────────────────
docker-up:
	docker-compose up --build -d
	@echo "Services started. API: http://localhost:8000"
	@echo "Webhook endpoint: http://localhost:8000/webhook/github"

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f

docker-restart:
	docker-compose restart api worker

# ── Cleanup ───────────────────────────────────────────────────────────────────
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	rm -f .coverage
