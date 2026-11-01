# `docker compose` (v2 plugin) when present, else the standalone docker-compose.
COMPOSE := $(shell docker compose version >/dev/null 2>&1 && echo "docker compose" || echo docker-compose)

.PHONY: insights-report gate gate-baseline stack-up stack-wait stack-down stack-logs stack-smoke \
	stack-lifecycle redrive test test-compose demo demo-resilience gate-report

stack-up: ## Start the token-free local stack in the background (API on :8080)
	$(COMPOSE) up --build -d

stack-wait: ## Block until the API and fake-gemini answer
	uv run python scripts/stack_client.py wait

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

test-compose: ## Failure-injection suite (11 scenarios) on a fresh local stack, then stop it
	$(MAKE) stack-down
	$(MAKE) stack-up
	$(MAKE) stack-wait
	uv run pytest tests/compose -m compose; status=$$?; \
		[ $$status -eq 0 ] || $(COMPOSE) logs --no-color --tail=150; \
		$(MAKE) stack-down; exit $$status

demo: ## End-to-end demo, no credentials: stack up, one sample invoice, print the JSON, stack down
	$(MAKE) stack-up
	$(MAKE) stack-wait
	uv run python scripts/demo.py; status=$$?; \
		[ $$status -eq 0 ] || $(COMPOSE) logs --no-color --tail=100; \
		$(MAKE) stack-down; exit $$status

gate-report: ## Regenerate the README gate report from data/baseline.json
	uv run python scripts/gate_report.py

demo-resilience: ## Watch the stack survive injected failures (starts it if needed)
	$(MAKE) stack-up
	uv run python scripts/demo_resilience.py

insights-report: ## Markdown report of the deployed stack from CloudWatch Logs Insights (AWS credentials)
	uv run scripts/insights_report.py --output insights-report.md

gate: ## Regression gate on the Test Set (live Gemini; needs GATE_GEMINI_API_KEY)
	uv run scripts/regression_gate.py

gate-baseline: ## Accept the current run as the new data/baseline.json (review the diff in the PR)
	uv run scripts/regression_gate.py --update-baseline

test: ## Unit and in-process seam tests (the compose tests run with test-compose)
	uv run pytest
	uv run lint-imports
