.DEFAULT_GOAL := help
COMPOSE = docker compose -f infra/docker-compose.yml

.PHONY: help dev stop build test lint types check install demo clean

help:  ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

# ─── Development ─────────────────────────────────────────────────────────────
dev:  ## Start full stack (api + postgres + frontend) with hot reload
	$(COMPOSE) up --build

stop:  ## Stop and remove containers
	$(COMPOSE) down

build:  ## Build all Docker images without starting
	$(COMPOSE) build

# ─── Local Python (without Docker) ───────────────────────────────────────────
install:  ## Install Python package in editable mode with dev extras
	cd backend && uv pip install -e ".[dev]"

api:  ## Run FastAPI locally (no Docker)
	cd backend && uvicorn udc.api.app:app --reload --port 8000

# ─── Quality ──────────────────────────────────────────────────────────────────
lint:  ## Run ruff linter + formatter check
	cd backend && uv run ruff check src/ && uv run ruff format --check src/

types:  ## Run mypy type checks
	cd backend && uv run mypy src/udc

test:  ## Run pytest test suite
	cd backend && uv run pytest ../tests/ -v --tb=short --cov=src/udc --cov-report=term-missing

check: lint types test  ## Run all quality checks (lint + types + tests)

# ─── Demo ─────────────────────────────────────────────────────────────────────
demo:  ## Seed demo data and run the end-to-end demo (Phase 6)
	@echo "Demo script not yet implemented — see Phase 6"

# ─── Housekeeping ─────────────────────────────────────────────────────────────
clean:  ## Remove __pycache__, .mypy_cache, .ruff_cache, .pytest_cache
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
