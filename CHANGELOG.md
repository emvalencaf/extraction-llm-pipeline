# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Entries are added
under `Unreleased` in the PR that makes the change, and moved under a dated
heading when `development` is released to `master`.

## [Unreleased]

### Added
- `scripts/deploy-infra.sh up` writes `GEMINI_API_KEY` to the SSM parameter after apply (through a
  pipe, never the state), and warns loudly when the key is missing.
- `scripts/wizard-post-merge-setup.sh`: resumable wizard for the manual setup of the observability
  and gate work (gate secrets, branch-protection check, `ALERT_EMAIL`; SNS confirmation and Billing tag only after a deploy).

- Manual setup with no Terraform home is documented in the README and in
  `scripts/wizard-gemini-key.sh`: activating the `Project` cost allocation tag in Billing, and
  the gate's `GATE_GEMINI_API_KEY`, `KAGGLE_USERNAME`, `KAGGLE_KEY` secrets and
  `GATE_KAGGLE_DATASET` variable.
- Regression-gate workflow (#39): `.github/workflows/regression-gate.yml` runs
  `scripts/regression_gate.py` only when extraction-affecting paths change (domain,
  application, composition, Prompt Bundle, adapters, Test Set split, baseline,
  gate script, locked dependencies). It uses the gate's own Google project key
  (`GATE_GEMINI_API_KEY`), downloads the Kaggle fixture (secrets `KAGGLE_USERNAME` and
  `KAGGLE_KEY`, variable `GATE_KAGGLE_DATASET`), and fails the check on a regression, the
  floor or an inconclusive run. Fork PRs get no secret and fail safe; only the comment job
  has `pull-requests: write`. `scripts/sticky_comment.py` posts the report as one sticky PR
  comment found by its hidden marker and updated in place. `ci_seeded_violations.sh` seeds
  workflow-hardening and sticky-logic violations.
- `ci` workflow (#38): adds `terraform fmt`/`validate` (root and bootstrap stacks, no backend)
  and `actionlint` jobs next to ruff, unit tests, import-linter and the compose-stack tests
  (fake-gemini only, no Gemini key). Public-repo hardening: read-only `contents` permission,
  no secrets in the workflow (fork PRs get none), `pull_request` trigger only, actions pinned
  to commit SHAs, concurrency cancel. A `seeded-violations` job runs `scripts/ci_seeded_violations.sh`, which proves each check
  fails on a seeded violation.
- Observability module (#37): `infra/modules/observability` with 8 alarms (`job-failed`,
  `llm-call-errors`, `job-duration-high`, `grounding-rate-low` on the EMF metrics;
  `dlq-not-empty`, `queue-age-high`, `worker-errors`, `api-errors` on SQS and Lambda), a
  dashboard, a single SNS `alerts` topic with an email subscription and a USD 10 budget
  filtered by the `Project` tag, wired in `infra/main.tf`. `alert_email` is a new required
  variable (`ALERT_EMAIL` for `scripts/deploy-infra.sh`). `docs/runbook.md` has one entry per
  alarm; a test checks that the metric names match what the app emits and that every alarm
  has a runbook entry.
- Failure-injection suite and `make demo-resilience` (#34): the 11 scenarios of #23 run as
  compose tests (`make test-compose`, marker `compose`) driven only by `fake-gemini` and
  environment variables. `fake-gemini` gains `POST/DELETE /control/scenario` (modes `error`,
  `reply`, `crash`; model targeting; call counts) and `GET /control/calls`. The model retry
  timings are read from `LLM_MAX_ATTEMPTS`, `LLM_BACKOFF_BASE_SECONDS` and
  `LLM_BACKOFF_CAP_SECONDS`; compose compresses them with the queue and upload TTL timings.
  The demo prints scenarios 1, 2, 4 and 5 as a timeline.
- Regression gate (#35): `scripts/regression_gate.py` runs the real graph on the Test Set
  (temperature 0, model calls paced to 12 RPM, key of its own Google project in
  `GATE_GEMINI_API_KEY`), scores deterministic assayer metrics (per field, line items,
  all-correct rate; no judge) and compares with the committed `data/baseline.json`. It fails
  on a regression of more than one document, below the absolute floor, or on an inconclusive
  run (quota errors, missing results), writes a Markdown report for the sticky PR comment and
  updates the baseline with `--update-baseline`. Verdict logic is `domain/gate.py`; the three
  required assayer changes are listed in `docs/assayer-required-changes.md`. The first
  baseline still has to be recorded with a live run.
- Terraform core and image packaging (#36): `infra/` with a `bootstrap/` stack (S3 state
  bucket) and modules `storage`, `queue` (jobs queue, DLQ with 5 receives, S3 notification
  policy), `jobs-table`, `registry` (ECR), `secrets` (SSM SecureString for the Gemini key),
  `worker` (SQS trigger: batch 1, concurrency 2, partial batch responses) and `api` (REST API,
  API key, usage plan 1 req/s burst 2, GET throttled apart at 20/40, 15-minute presigned
  PUT). One `prod` environment in us-east-1, S3-native state locking, `force_destroy`
  everywhere, committed provider lock files. `scripts/deploy-infra.sh` (`bootstrap`, `up`
  ECR-first, `plan`, `down`). `init_resources.check_against_terraform` now checks
  `infra/` against the local resource names. The runtime reads the Gemini key from the SSM
  parameter named by `GEMINI_API_KEY_SSM_PARAMETER`. Measured on the shared image
  (local docker, 2026-10-31): 947 MB on disk, about 357 MB compressed; cold start about
  6.1 s for the worker (init 2.2 s plus 5.6 s building the service with Presidio and
  spaCy), 10 ms warm. Known gap: an API Gateway quota is plan-wide, so `daily_quota`
  (default 1000) counts GET polling as well; the 100 POST/day limit is enforced only by
  the local shim.
- Async job lifecycle (#33): the full state machine (`awaiting_upload`, `queued`,
  `processing`, `succeeded`, `failed_validation`, `failed`, `expired`) enforced by
  conditional DynamoDB writes against a domain transition table; optional
  `Idempotency-Key` on `POST /jobs` (200 with the first job on replay); duplicate
  deliveries are skipped; uploads that never arrive turn `expired`. Queue behavior:
  batch 1, 5 receives before the DLQ, 2 workers, visibility delay doubling per receive
  on `ModelUnavailableError`, job marked `failed` on the last receive, worker-side
  size check before download, and `make redrive` (native `StartMessageMoveTask`) that
  re-runs jobs which failed by retries exhausted. The API shim emulates the API key
  and usage plan with JSON 403/429 bodies; fake-gemini gains `PUT /control/fail`.
  `make stack-lifecycle` runs the poison, redrive, idempotency and 403/429 scenarios.
- Follow-ups to #29: few-shot examples are now anonymized with the same detector and
  `[TYPE_n]` placeholders real inputs get (`scripts/build_fewshots.py`, regenerated
  `examples.json`; a test checks no detected identifier remains). All three models run
  at temperature 0, including `gemini-3.8-flash`. Evidence (checked 2026-10-31): Google's
  Gemini 3 guide (https://ai.google.dev/gemini-api/docs/gemini-3) recommends keeping
  temperature at the default 1.0 and warns that lower values "may lead to unexpected
  behavior, such as looping or degraded performance"; it does not say the API rejects
  other values, and no source found says so. No live API call was made, so acceptance
  is unconfirmed: if the API returns a 400, set `temperature` back to `null` in
  `prompts/settings.json`. The Prompt Version changes. `composition/runtime.py` uses
  the real Gemini adapter when `GEMINI_API_KEY` is set, else `FAKE_GEMINI_URL`.

- Walking skeleton (#28): hexagonal package `src/invoice_extraction/` with the
  Extraction Schema (Decimal/ISO normalization in code), the `ExtractInvoice`
  pipeline use case, in-process `FakeGemini`, pytest seam-1 tests, import-linter
  layer contracts, and `tests` and `architecture` CI jobs.
- Pre and post slots (#30): PDF guards (5 MB, 10 pages) ending with a
  `TerminalReason`, text cleanup, reversible `[TYPE_n]` Anonymization through a
  Presidio adapter (pattern recognizers for GSTIN, PAN, tax ids, email, phone, bank
  account, company names and Indian postal addresses, on a blank spaCy pipeline so
  no model download), an in-memory never-persisted Placeholder map, exact-string
  Restore and an output guardrail. Tests cover Leak Rate and the round trip.
- Gemini extraction (#29): `GeminiExtractionModel` adapter; a Prompt Bundle (system
  prompt, repair prompt, model settings, static Train Set few-shots) shipped in
  `src/invoice_extraction/prompts/` and versioned by content hash, attached to every
  `PipelineResult`; the pipeline is now a LangGraph graph (no checkpointer) with pre
  and post slots as nodes, primary, fallback and escalation models, a validation
  repair loop and jittered transient retries. `temperature` is omitted per model where
  unsupported. `FakeGemini` gains model-targeted failure injection (`inject`).
- Observability (#31): runtime Grounding Rate over non-anonymized fields (informational,
  never blocking) on `PipelineResult` and the `job` event; one `llm_call` wide event
  per Gemini call and one `job` event per job, through an `EventSink` port with a
  `JsonEventSink` adapter (one JSON line each, EMF metrics without dimensions). Events
  carry ids, counts, timings and field paths only; a test checks no invoice content
  reaches any log line. `ExtractionModel.extract` now returns a `ModelReply` with token
  usage.
- `domain/ground_truth.py`: one pure function mapping a Kaggle ground-truth record to
  an Extraction Schema shaped dict, reused for few-shots
  (`scripts/build_fewshots.py`) and, later, the regression gate.

### Fixed

- The `job-failed` alarm watches the new `JobInfraFailed` metric (outcomes other than
  `succeeded` and `failed_validation`), so a bad PDF no longer pages; `JobFailed` stays on the
  dashboard.
- The local poller deleted the message when a Lambda invoke came back as a function error
  (for example a timeout): it now leaves it for redelivery, as the real event source mapping
  does.
- Lambda image installs from `uv.lock` (including `google-genai`) and the SDK import is
  lazy, so `api_handler` and `worker_handler` start; verified with the local stack.
- On the last receive any processing exception marks the job `failed`
  (`retries_exhausted`); any non-business error hides the message for a growing delay. A
  hard Lambda timeout cannot be caught, so such a job stays `processing`.
- An unavailable escalation model raises `ModelUnavailableError` (retried by the queue)
  instead of ending as `failed_validation`.
- `stack_client.worker_events` orders the wide events by emit time (`_aws.Timestamp`):
  `compose logs` prints one worker's lines after the other's, so a job's events could come
  back out of order; covered by `tests/test_stack_client.py`.

### Changed

- Review fixes for the gate, resilience and infra work: the API usage plan throttles POST
  (1 rps, burst 2) and GET (20/40) per method through `api_stages.throttle`, with the plan
  ceiling at the larger of the two, so the GET limit is no longer capped by the POST one;
  the image size and cold start measurements are recorded in `infra/README.md` and the
  README (local, not measured on Lambda); `ExtractInvoice.prompt_version` is public and the
  gate no longer reads a private attribute; the gate uses a `TestDocument` dataclass, scores an
  invalid extraction in `score_document` (one place) and has tests that a quota or model
  outage in the real graph is inconclusive while an unreadable PDF is a conclusive miss;
  `assayer_scoring` shares field lists between `FIELD_MAP` and the amount keys;
  `stack_client` reads the model names from `prompts/settings.json`; the runtime retry
  policies share an environment helper.
- Commit titles have no length limit: removed the 72-character check from the `commit-msg`
  hook (also run by CI) and from CONTRIBUTING.md.
- Redrive and final-state rules and a `RetryPolicy` (defaults in one place, built once
  from the environment) live in `domain/status.py`; the `idem#` key scheme stays in the
  DynamoDB adapter; handlers and the poller log through `logging` without invoice content.
- Review smells (#27), no behavior change: jobs are a typed `Job` dataclass and status
  changes take a typed `JobUpdate` instead of `**fields: Any`; the worker handler parses
  the receive count and S3 key in small helpers; queue-name/URL handling
  (`composition/queues.py`) and API proxy-event parsing (`entrypoints/http_events.py`) are
  shared instead of duplicated; `JobService.jobs` is private; optional collaborators
  (`delayer`, `presign_client`, `S3_PUBLIC_ENDPOINT_URL`) are kept and now say why.
- `ExtractionModel.extract` takes an `ExtractionRequest`; `ExtractInvoice` takes a
  `PromptBundle`; `build_extract_invoice` accepts retry, repair, sleep and rng options.

- Token-free local stack (#32): `compose.yaml` with Lambda RIE (API and two worker
  containers), DynamoDB Local, moto (S3), ElasticMQ, an HTTP `fake-gemini` with a
  control endpoint, a poller (S3 event relay skipping `s3:TestEvent`, URL-decoded keys,
  one worker per RIE container), a FastAPI API shim and a boto3 `init`. `make stack-up`
  starts it, `make stack-smoke` runs create job, presigned PUT, fetch result. Adds
  `JobService`, API and worker Lambda handlers, DynamoDB/S3/HTTP-model adapters and
  in-process seam-2 tests on moto. The `init` Terraform check is stubbed until
  `infra/terraform` exists.

- Split Manifest (seed 42, 60/20/20 stratified by line-item count) and its generator
  `scripts/make_split_manifest.py`.
- Live Gemini Placeholder preservation test and its write-up in
  `docs/experiments/gemini-placeholder-preservation.md` (140/140 verbatim on the
  Validation Set).
- `kaggle` (dev) and `google-genai` dependencies; `data/kaggle/` is git-ignored.
- `implement-spec` accepts an optional ticket range or list (e.g. `28-33`) to implement
  only a subset of a spec's tickets, leaving the spec and other tickets open.

## [0.2.0] - 2026-10-23

### Added

- `usage-report` shows the session recaps Claude Code writes when you step away:
  every recap of a session, verbatim, in the Sessions table and the Work cards.
  Adds `tests/test_usage_recaps.py` (`uv run --with pytest pytest tests`).

### Changed

- The `okf` skill is split by mode into `wiki-okf-produce`, `wiki-okf-maintain`
  and `wiki-okf-consume`; `wiki-okf` stays as a non-invocable core holding the
  conformance rule, conventions, `SPEC.md`, the v0.2 families reference and the
  templates. `okf_init.py` moved to `wiki-okf-produce`.
- `validate`, `visualize`, `query` and `backfill` renamed to `wiki-okf-validate`,
  `wiki-okf-visualize`, `wiki-okf-query` and `wiki-okf-backfill`. The `/okf`
  command no longer exists and has no alias. The pre-commit hook, CI,
  `ask-harness` and the README use the new names.
- These skills are now a local fork of
  [scaccogatto/okf-skills](https://github.com/scaccogatto/okf-skills), so their
  entries were removed from `skills-lock.json`.
- `ask-matt` and `setup-matt-pocock-skills` removed; `ask-harness` and
  `setup-project-harness` carry `metadata.source` and `metadata.derived-from`
  crediting them, as do the `wiki-okf-*` skills for `scaccogatto/okf-skills`.
- `README.md` restructured after
  [Best-README-Template](https://github.com/othneildrew/Best-README-Template).
- `setup-project-harness` now generates the project's own README from
  `README.template.md`, which follows the same structure.
- `CODE_STANDARDS.md` and `AGENTS.md`: documentation standard for READMEs.
- `setup-project-harness` synced with the updated `setup-matt-pocock-skills`:
  `GLOSSARY.md` / `GLOSSARY-MAP.md` replace `CONTEXT.md` / `CONTEXT-MAP.md`, the
  GitHub and GitLab tracker templates are refreshed, and missing triage labels
  are created on the tracker.
- `ask-harness` synced with `ask-matt`: `GLOSSARY.md` naming, plus `/prototype`,
  `/implement-spec`, `/pr`, `/retro` and `/teach`.
- Skills that told users to run `/setup-matt-pocock-skills` now point to
  `/setup-project-harness`.
- Every skill keeps supporting files in `scripts/`, `references/` and `assets/`
  instead of the skill root (`okf/reference` and `okf/templates` renamed to
  `references` and `assets`); `CODE_STANDARDS.md` documents the layout.

## [0.1.0] - 2026-09-20

First release of the project template.

### Added

- Template scaffolding: `README.md` with step-by-step instructions for using the
  template, `.gitignore`, `.editorconfig`, `pyproject.toml` (ruff), `.wiki/` OKF
  knowledge bundle, PR template and commit template.
- `CONTRIBUTING.md` (branch strategy and commit convention), `CODE_STANDARDS.md`
  and this changelog.
- Git hooks in `.githooks/`: `commit-msg` enforces the commit format;
  `pre-commit` checks Unicode, runs ruff, and updates `.wiki/` automatically
  (via `claude -p`, with one validator-guided retry) with strict validation.
  Skip the wiki update with `SKIP_WIKI_UPDATE=1`.
- Scripts: `scripts/setup.sh`, `scripts/protect-master.sh`,
  `scripts/check_unicode.py`, `scripts/set-budget.sh`,
  `scripts/usage-tracking.sh` and `scripts/usage_log.sh`.
- GitHub Actions CI (`.github/workflows/ci.yml`): PR target rule (only
  `development` may target `master`), Unicode, ruff, `.wiki/` validation and
  commit message format checks.
- Project-level status line (`.claude/settings.json` and `scripts/statusline.sh`)
  showing project, model, branch (dirty and ahead/behind markers, red on
  `master`/`main`/`development`), context, cost or budget, rate limits,
  duration and session id. `scripts/set-budget.sh` sets, shows or clears the USD
  budget used for pay-per-token accounts (project or `--global`).
- Per-session usage log: the status line writes `.claude/usage/<session>.json`
  (git-ignored) when enabled with `scripts/usage-tracking.sh on|off|status`.
- `query` skill: natural-language search over OKF bundles, with `--limit` and
  metadata filters (`--type`, `--tag`, `--status`, `--path`, `--generated-by`,
  `--verified-by`, `--resource`, `--source`, `--stale`/`--fresh`,
  `--verified`/`--unverified`, `--include-deprecated`).
- `usage-report` skill: local HTML dashboard with tabs (Overview, Work, By type,
  Sessions). Tokens in and out per day, session and skill, duration, model,
  effort, context peak, top skills, heuristic intents and tool usage (names,
  calls, errors, time). The Work tab groups sessions by spec, ticket, feature
  directory or branch across the grill, spec, tickets, implement and review
  flow, resolves local `.scratch/` files and GitHub issues, and links commits
  through the `Session-Id` trailer (`--tracker`, `--offline`). Subagents appear
  as separate rows linked to their session and are never added to its totals. The
  By type tab classifies work as feature, bug fix, refactor, etc. from commit
  tags, branch prefix, GitHub labels or the opening skill. The logged cost is
  always labelled an estimate.

### Changed

- Renamed `ask-matt` to `ask-harness` and extended it to route the OKF skills
  (`query`, `okf`, `validate`, `visualize`, `backfill`), `usage-report` and the
  repo workflow. Dropped the `/prototype` and `/teach` references, which are not
  in this repo.
- Renamed `setup-matt-pocock-skills` to `setup-project-harness`; it now also sets
  the project name and description, configures `CODE_STANDARDS.md` with the
  matching `pyproject.toml` settings, and asks whether to keep usage tracking on
  and, for pay-per-token users, the status line budget.
- Moved the knowledge bundle from `.okf/` to `.wiki/`.
