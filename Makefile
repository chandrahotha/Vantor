.PHONY: help install lint lint-backend lint-worker lint-frontend typecheck typecheck-backend typecheck-frontend \
	test test-backend test-worker test-frontend test-pg test-e2e build build-frontend audit audit-python audit-js \
	verify verify-gates verify-full contract up down clean

# The single definition of every command CI also runs. `.github/workflows/ci.yml`
# invokes these targets rather than repeating the command lines: the last time
# the two diverged, `make test` reported green while four worker tests skipped,
# because the Makefile did not pass the Redis URL that CI did. If a target and a
# CI step ever disagree, that is the bug — fix the target and have CI call it.

PYTHON ?= $(shell which python3 2>/dev/null || which python 2>/dev/null || echo python)
RUFF ?= $(shell which ruff 2>/dev/null || echo ruff)
MYPY ?= $(shell which mypy 2>/dev/null || echo mypy)
# Both shipped requirement files by default; CI narrows it to the one each job
# installed, so the backend job never audits dependencies it does not have.
REQUIREMENTS ?= backend/requirements.txt worker/requirements.txt

help: ## Show this help message
	@echo "Vantor — Available Makefile Targets:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install frontend and backend dependencies
	@echo "Installing backend dependencies..."
	cd backend && $(PYTHON) -m pip install -r requirements.txt
	@echo "Installing worker dependencies..."
	cd worker && $(PYTHON) -m pip install -r requirements.txt
	@echo "Installing contract tooling (PyYAML — renders api/openapi.yaml)..."
	$(PYTHON) -m pip install "pyyaml==6.0.3"
	@echo "Installing frontend dependencies..."
	npm --prefix frontend ci

lint-backend: ## Ruff over the backend
	$(RUFF) check backend/app backend/tests backend/alembic

lint-worker: ## Ruff over the worker
	$(RUFF) check worker

lint-frontend: ## ESLint over the web app
	npm --prefix frontend run lint

lint: lint-backend lint-worker lint-frontend ## Run all linters

typecheck-backend: ## Mypy over the backend application
	$(MYPY) backend/app

typecheck-frontend: ## tsc over the web app
	npm --prefix frontend run typecheck

typecheck: typecheck-backend typecheck-frontend ## Run all type checkers

test-backend: ## Backend suite, the fast tier (SQLite — no RLS, see test-pg)
	APP_ENV=test DATABASE_URL="sqlite://" OIDC_ISSUER="https://issuer.test/realms/vantor" JWT_AUDIENCE="vantor-web" $(PYTHON) -m pytest backend/tests -q

test-worker: ## Worker suite. Without RQ_TEST_REDIS_URL the four live-Redis tests skip; STRICT=1 forbids that (CI).
	cd worker && $(PYTHON) ../scripts/run_tier.py --name "Worker tier" \
	  --min-passed $(if $(STRICT),38,34) $(if $(STRICT),,--allow-skips) \
	  -- $(PYTHON) -m pytest tests -q

test-frontend: ## Web app unit components (vitest)
	npm --prefix frontend run test

test: test-backend test-worker test-frontend ## Run every suite that needs no services
	@echo ""
	@echo "Covered by 'make test': the SQLite backend tier, the worker tests that do"
	@echo "not need Redis, and the vitest suite."
	@echo "NOT covered — run these explicitly, they are the ones that have historically"
	@echo "been mistaken for the above:"
	@echo "  make test-pg     row-level security, composite foreign keys, real concurrency"
	@echo "  make test-e2e    the Playwright procurement flow and the axe accessibility run"
	@echo "  make audit       pip-audit and npm audit"

test-pg: ## The Postgres tier: needs PG_TEST_DATABASE_URL pointing at a real cluster
	@test -n "$$PG_TEST_DATABASE_URL" || { \
	  echo "PG_TEST_DATABASE_URL is not set. This tier is the only proof of row-level"; \
	  echo "security, composite foreign keys and real concurrency — SQLite cannot see"; \
	  echo "any of them. Point it at a scratch Postgres, e.g.:"; \
	  echo "  docker compose up -d postgres && export PG_TEST_DATABASE_URL=..."; \
	  exit 1; }
	cd backend && APP_ENV=test $(PYTHON) ../scripts/run_tier.py --name "Postgres tier" --min-passed 11 -- $(PYTHON) -m pytest -m pg -q

test-e2e: ## Playwright flows + axe. Needs a built app and the API reachable.
	cd frontend && $(PYTHON) ../scripts/run_tier.py --name "e2e tier" --format playwright \
	  --min-passed 5 --allow-skips -- npm run test:e2e

build-frontend: ## Production Next.js bundle
	npm --prefix frontend run build

build: build-frontend ## Build the shipped artifacts

audit-python: ## pip-audit over a requirements file (strict). REQUIREMENTS=... to narrow it.
	@for r in $(REQUIREMENTS); do \
	  echo "pip-audit: $$r"; \
	  $(PYTHON) -m pip_audit -r $$r --strict || exit 1; \
	done

audit-js: ## npm audit over the web app (production deps, high and above)
	# Production surface only: dev-only findings with no upstream patch (e.g.
	# braces via eslint) are tracked via Dependabot, not by this gate.
	npm --prefix frontend audit --omit=dev --audit-level=high

audit: audit-python audit-js ## Dependency audits

verify: ## Run full repository verification pipeline
	@bash scripts/verify_all.sh

verify-gates: ## Only the repository hygiene gates (no builds, no suites)
	$(PYTHON) scripts/check_secrets.py
	$(PYTHON) scripts/check_mojibake.py
	$(PYTHON) scripts/verify_doc_links.py
	$(PYTHON) scripts/audit_migrations.py
	$(PYTHON) scripts/pin_digests.py --check
	$(PYTHON) scripts/check_ci_consistency.py --check
	$(PYTHON) scripts/doc_counts.py --check

contract: ## Regenerate the committed OpenAPI contract (api/openapi.json + .yaml)
	$(PYTHON) scripts/generate_openapi.py

up: ## Start the hardened local development stack via Docker Compose
	docker compose up -d --build

down: ## Stop Docker Compose containers
	docker compose down

clean: ## Remove temporary build caches and test artifacts
	rm -rf frontend/.next frontend/out .pytest_cache backend/.pytest_cache worker/.pytest_cache .ruff_cache backend/.ruff_cache worker/.ruff_cache .mypy_cache backend/.mypy_cache
