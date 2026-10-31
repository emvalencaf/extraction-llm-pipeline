# `docker compose` (v2 plugin) when present, else the standalone docker-compose.
COMPOSE := $(shell docker compose version >/dev/null 2>&1 && echo "docker compose" || echo docker-compose)

.PHONY: stack-up stack-down stack-logs stack-smoke test

stack-up: ## Start the token-free local stack in the background (API on :8080)
	$(COMPOSE) up --build -d

stack-down: ## Stop the stack and remove its containers
	$(COMPOSE) down --remove-orphans

stack-logs: ## Follow the logs of every service
	$(COMPOSE) logs -f

stack-smoke: ## Run the happy path against a running stack
	uv run python scripts/stack_smoke.py

test: ## Unit and in-process seam tests
	uv run pytest
	uv run lint-imports
