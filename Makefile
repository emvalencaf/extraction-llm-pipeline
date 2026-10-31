# `docker compose` (v2 plugin) when present, else the standalone docker-compose.
COMPOSE := $(shell docker compose version >/dev/null 2>&1 && echo "docker compose" || echo docker-compose)

.PHONY: stack-up stack-down stack-logs stack-smoke stack-lifecycle redrive test

stack-up: ## Start the token-free local stack in the background (API on :8080)
	$(COMPOSE) up --build -d

stack-down: ## Stop the stack and remove its containers
	$(COMPOSE) down --remove-orphans

stack-logs: ## Follow the logs of every service
	$(COMPOSE) logs -f

stack-smoke: ## Run the happy path against a running stack
	uv run python scripts/stack_smoke.py

stack-lifecycle: ## Poison message, redrive, idempotency and 403/429 against a running stack
	uv run python scripts/stack_lifecycle.py

redrive: ## Replay the DLQ with native SQS redrive (stack must be up)
	$(COMPOSE) run --rm --no-deps init \
		python -m invoice_extraction.entrypoints.redrive

test: ## Unit and in-process seam tests
	uv run pytest
	uv run lint-imports
