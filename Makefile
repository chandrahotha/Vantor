.PHONY: help install lint typecheck test test-backend test-frontend test-worker build verify up down clean

PYTHON ?= $(shell which python3 2>/dev/null || which python 2>/dev/null || echo python)
RUFF ?= $(shell which ruff 2>/dev/null || echo ruff)
MYPY ?= $(shell which mypy 2>/dev/null || echo mypy)

help: ## Show this help message
	@echo "Vantor — Available Makefile Targets:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Install frontend and backend dependencies
	@echo "Installing backend dependencies..."
	cd backend && $(PYTHON) -m pip install -r requirements.txt
	@echo "Installing worker dependencies..."
	cd worker && $(PYTHON) -m pip install -r requirements.txt
	@echo "Installing frontend dependencies..."
	npm --prefix frontend install

lint: ## Run linters across backend, worker, and frontend
	$(RUFF) check backend/app backend/tests backend/alembic
	$(RUFF) check worker
	npm --prefix frontend run lint

typecheck: ## Run static type checkers (mypy, tsc)
	$(MYPY) backend/app
	npm --prefix frontend run typecheck

test-backend: ## Run backend unit & integration tests
	APP_ENV=test DATABASE_URL="sqlite://" OIDC_ISSUER="https://issuer.test/realms/vantor" JWT_AUDIENCE="vantor-web" $(PYTHON) -m pytest backend/tests -q

test-worker: ## Run background worker unit tests
	$(PYTHON) -m pytest worker/tests -q

test-frontend: ## Run frontend test suite
	npm --prefix frontend run test

test: test-backend test-worker test-frontend ## Run all test suites

build: ## Build frontend production Next.js bundle
	npm --prefix frontend run build

verify: ## Run full repository verification pipeline
	@bash scripts/verify_all.sh

up: ## Start the hardened local development stack via Docker Compose
	docker compose up -d --build

down: ## Stop Docker Compose containers
	docker compose down

clean: ## Remove temporary build caches and test artifacts
	rm -rf frontend/.next frontend/out .pytest_cache backend/.pytest_cache worker/.pytest_cache .ruff_cache backend/.ruff_cache worker/.ruff_cache .mypy_cache backend/.mypy_cache
