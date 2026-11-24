.DEFAULT_GOAL := help
COMPOSE = docker compose -f infra/docker-compose.yml

.PHONY: help dev stop build test lint types check install demo demo-api demo-record mcp-install mcp-dev mcp-test clean

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
	cd ../backend && uv pip install -e ".[dev]"

api:  ## Run FastAPI locally (no Docker)
	cd ../backend && uvicorn udc.api.app:app --reload --port 8000

# ─── Quality ──────────────────────────────────────────────────────────────────
lint:  ## Run ruff linter + formatter check
	cd ../backend && uv run --extra dev ruff check src/ && uv run --extra dev ruff format --check src/

types:  ## Run mypy type checks
	cd ../backend && uv run --extra dev mypy src/udc

test:  ## Run pytest test suite
	cd ../backend && uv run --extra dev pytest ../tests/ -v --tb=short --cov=src/udc --cov-report=term-missing

check: lint types test  ## Run all quality checks (lint + types + tests)

# ─── Demo ─────────────────────────────────────────────────────────────────────
demo:  ## Seed demo data and run the end-to-end demo (Phase 6)
	@echo "Demo script not yet implemented — see Phase 6"

DEMO_DB = ../data/demo.duckdb

demo-api:  ## Run the API on :8000 with the retail demo data (fresh DuckDB file each start)
	cd ../backend && rm -f $(DEMO_DB) $(DEMO_DB).wal && \
	  DUCKDB_PATH=$(DEMO_DB) SEED_DEMO=true \
	  DATABASE_URL=$${DATABASE_URL:-postgresql://unused@localhost/unused} \
	  uv run uvicorn udc.api.app:app --port 8000

demo-record:  ## Re-record the demo mapping proposals with live Claude calls (needs ANTHROPIC_API_KEY)
	cd ../backend && DATABASE_URL=$${DATABASE_URL:-postgresql://unused@localhost/unused} \
	  uv run python -m udc.demo record

# ─── MCP app (mcp-app/, Skybridge) ────────────────────────────────────────────
mcp-install:  ## Install the MCP app's dependencies
	cd ../mcp-app && npm install

mcp-dev:  ## Run the MCP app on :3000 (MCP at /mcp, DevTools at /); needs `make demo-api`
	cd ../mcp-app && npm run dev

mcp-test:  ## Type-check and test the MCP app
	cd ../mcp-app && npm run typecheck && npm test

# ─── Housekeeping ─────────────────────────────────────────────────────────────
clean:  ## Remove __pycache__, .mypy_cache, .ruff_cache, .pytest_cache
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
