<a id="readme-top"></a>

<!--
Structure adapted from https://github.com/othneildrew/Best-README-Template
-->

<br />
<div align="center">
  <h3 align="center">Invoice extraction pipeline</h3>

  <p align="center">
    Turns invoice PDFs into validated, structured JSON with an LLM, on AWS, and gates
    every change against a measured regression baseline.
    <br />
    <a href="docs/runbook.md"><strong>Explore the docs »</strong></a>
    <br />
    <br />
    <a href="https://github.com/emvalencaf/extraction-llm-pipeline/issues/new">Report Bug</a>
    &middot;
    <a href="https://github.com/emvalencaf/extraction-llm-pipeline/issues/new">Request Feature</a>
  </p>
</div>

<details>
  <summary>Table of Contents</summary>
  <ol>
    <li>
      <a href="#about-the-project">About The Project</a>
      <ul>
        <li><a href="#how-it-works">How it works</a></li>
        <li><a href="#built-with">Built With</a></li>
      </ul>
    </li>
    <li>
      <a href="#getting-started">Getting Started</a>
      <ul>
        <li><a href="#prerequisites">Prerequisites</a></li>
        <li><a href="#installation">Installation</a></li>
      </ul>
    </li>
    <li>
      <a href="#usage">Usage</a>
      <ul>
        <li><a href="#local-stack">Local stack</a></li>
        <li><a href="#job-flow">Job flow</a></li>
        <li><a href="#regression-gate-report">Regression gate report</a></li>
        <li><a href="#infrastructure-aws">Infrastructure (AWS)</a></li>
        <li><a href="#deployment">Deployment</a></li>
        <li><a href="#pipeline-report-cloudwatch-logs-insights">Pipeline report</a></li>
      </ul>
    </li>
    <li>
      <a href="#development-workflow">Development workflow</a>
      <ul>
        <li><a href="#daily-workflow">Daily workflow</a></li>
        <li><a href="#status-line-budget">Status line budget</a></li>
        <li><a href="#usage-tracking-and-report">Usage tracking and report</a></li>
      </ul>
    </li>
    <li><a href="#roadmap">Roadmap</a></li>
    <li><a href="#contributing">Contributing</a></li>
    <li><a href="#license">License</a></li>
    <li><a href="#contact">Contact</a></li>
    <li><a href="#acknowledgments">Acknowledgments</a></li>
  </ol>
</details>

## About The Project

Send an invoice PDF to an API and get back a validated JSON of its seller, client, line
items and totals. The text is anonymized before it reaches the model (Gemini only sees
Placeholders such as `[NAME_1]`), the reply is validated against one schema, and a failed
validation is repaired or escalated to a stronger model before the job gives up. Business
failures end the job; only infrastructure failures retry through SQS and land in a
dead-letter queue.

Every change to the extraction path is checked by a deterministic regression gate against a
committed baseline, and deploys to AWS need that gate plus a human approval.

![AWS architecture](docs/diagrams/architecture.svg)

<p align="right">(<a href="#readme-top">back to top</a>)</p>

### How it works

The worker runs a LangGraph graph: `pre` checks and cleans the PDF text and anonymizes it,
`call` asks the model, `post` guards the reply and restores the real identifiers, and
`validate` checks the Extraction Schema. Terms are defined in [GLOSSARY.md](GLOSSARY.md);
the decisions behind them are the [ADRs](docs/adr).

![Extraction graph](docs/diagrams/extraction-graph.svg)

<p align="right">(<a href="#readme-top">back to top</a>)</p>

### Built With

* [Python](https://www.python.org) 3.11+ managed with [uv](https://docs.astral.sh/uv/)
* [LangGraph](https://langchain-ai.github.io/langgraph/), [Pydantic](https://docs.pydantic.dev), [FastAPI](https://fastapi.tiangolo.com)
* [Google Gemini](https://ai.google.dev) through `google-genai`
* [Presidio](https://microsoft.github.io/presidio/) for reversible anonymization
* [AWS](https://aws.amazon.com): API Gateway, Lambda (container images), S3, SQS, DynamoDB, SSM, CloudWatch
* [Terraform](https://www.terraform.io) and [GitHub Actions](https://docs.github.com/actions)
* [ruff](https://docs.astral.sh/ruff/) for lint and format

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Getting Started

### Prerequisites

[`git`](https://git-scm.com), [`uv`](https://docs.astral.sh/uv/), [Docker](https://www.docker.com)
with Compose (the local stack and `make demo`) and [`make`](https://www.gnu.org/software/make/).
To deploy: [Terraform](https://www.terraform.io) 1.10+, the [AWS CLI](https://aws.amazon.com/cli/)
and an AWS account. [`gh`](https://cli.github.com) and the [`claude`](https://claude.com/claude-code)
CLI are only needed for contributing (the `pre-commit` hook uses `claude` to update `.wiki/`).

### Installation

```bash
git clone https://github.com/emvalencaf/extraction-llm-pipeline.git
cd extraction-llm-pipeline
uv sync
scripts/setup.sh      # enables the git hooks, once per clone
make demo             # see it work: no credentials, no tokens
```

`make demo` builds the local stack, sends a sample invoice, prints the result JSON and
tears the stack down. Deploying to AWS is covered in [Infrastructure](#infrastructure-aws).

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Usage

### Local stack

A token-free stack (moto S3/SQS, DynamoDB local, ElasticMQ, a fake Gemini and the
Lambda images under the Runtime Interface Emulator) runs with Docker Compose. The API
listens on `:8080`. `make` picks `docker compose` (v2) or `docker-compose` (v1).

```bash
make demo             # one command, no credentials: up, sample invoice, result JSON, down
make stack-up         # build and start the stack in the background
make stack-smoke      # happy path: create a job, upload a PDF, poll until succeeded
make stack-lifecycle  # poison message, redrive, idempotency, 403 and 429
make redrive          # replay the dead-letter queue with native SQS redrive
make stack-down       # stop and remove the containers
make test-compose     # failure-injection suite: the 11 scenarios on a fresh stack
make demo-resilience  # watch scenarios 1, 2, 4 and 5 as a readable timeline
```

Failure injection uses only the `fake-gemini` control endpoint and environment variables
(`POST /control/scenario` with `mode` `error`, `reply` or `crash`, optionally limited to one
`model` and a number of `times`; `DELETE /control/scenario` clears it). `compose.yaml`
compresses the timings (backoff, queue delay, visibility timeout, upload TTL). The suite
takes about five minutes, most of it the two scenarios that wait on the queue: the DLQ
after quota exhaustion and the Lambda timeout on the last receive.

The Lambda image installs its dependencies from `uv.lock`.

### Job flow

A job moves `awaiting_upload` → `queued` → `processing` → `succeeded`, `failed_validation` or
`failed`. `make demo` and `make demo-resilience` show this flow on the local stack; the
queue lane below is what the failure-injection suite exercises.

![Job flow](docs/diagrams/job-flow.svg)

### Regression gate report

Accepted result of the [regression gate](.github/workflows/regression-gate.yml) on the Test
Set, generated from `data/baseline.json` by `make gate-report` (never edit it by hand).

<!-- gate-report:start -->
All-correct documents: **20/20** (floor 90%, tolerated drop 1, prompt version `954eaa0965a3e7d0`).

| Field | Score |
|---|---|
| client.address | 1.0000 |
| client.name | 1.0000 |
| client.tax_id | 1.0000 |
| currency | 1.0000 |
| invoice_no | 1.0000 |
| issue_date | 1.0000 |
| items.description | 1.0000 |
| items.gross_amount | 1.0000 |
| items.list_f1 | 1.0000 |
| items.list_precision | 1.0000 |
| items.list_recall | 1.0000 |
| items.net_amount | 1.0000 |
| items.quantity | 1.0000 |
| items.unit | 1.0000 |
| items.unit_price | 1.0000 |
| items.vat_pct | 1.0000 |
| seller.address | 1.0000 |
| seller.name | 1.0000 |
| seller.tax_id | 1.0000 |
| totals.gross_amount | 1.0000 |
| totals.net_amount | 1.0000 |
| totals.vat_amount | 1.0000 |
| totals.vat_pct | 1.0000 |
<!-- gate-report:end -->

### Infrastructure (AWS)

`infra/` holds the Terraform for one `prod` environment in `us-east-1`: `bootstrap/`
(state bucket, local state, run once), `modules/{storage,queue,jobs-table,registry,secrets,worker,api}`
and the root files that compose them. State uses S3-native locking (`use_lockfile`, no
DynamoDB table). Everything has `force_destroy`/`force_delete`, so anyone can create and
fully destroy it. `infra/locals.tf` holds the logical names the local `init` also creates;
`check_against_terraform` (run by `init` and by a test) fails when they drift.

```bash
export BUCKET_SUFFIX=<your-account-id>      # makes the S3 names yours
export ALERT_EMAIL=<you@example.com>        # alarms and budget; confirm the SNS email once
export GEMINI_API_KEY=<key>                       # written to SSM after apply; without it every job fails
scripts/deploy-infra.sh bootstrap           # state bucket + infra/backend.hcl, once
scripts/deploy-infra.sh up                  # ECR, build and push the image, everything else
aws ssm put-parameter --overwrite --type SecureString \
  --name "$(terraform -chdir=infra output -raw gemini_parameter_name)" --value <gemini-key>
scripts/deploy-infra.sh down                # destroy the stack, then the state bucket
```

The `observability` module adds 8 CloudWatch alarms, a dashboard, one SNS `alerts` topic
with an email subscription and a USD 10 budget filtered by the `Project` tag. Each alarm has
an entry in the [runbook](docs/runbook.md).

Run `scripts/wizard-post-merge-setup.sh` for all the manual steps in order (gate secrets, branch-protection check, `ALERT_EMAIL`; SNS confirmation and Billing tag only after a deploy). Two of them have no Terraform home (`scripts/wizard-gemini-key.sh` also walks through both):

- **Billing tag.** In the AWS Billing console, open Cost allocation tags and activate the
  user-defined `Project` tag, once per account and after the first deploy. Until then the
  budget sees no costs; activation takes up to 24 hours.
- **Regression-gate secrets.** In the GitHub repository settings add the Actions secrets
  `GATE_GEMINI_API_KEY` (a Google project key of its own, not the runtime one),
  `KAGGLE_USERNAME` and `KAGGLE_KEY`, and the Actions variable `GATE_KAGGLE_DATASET`
  (`owner/slug` of the invoice dataset). Without them the
  [regression gate](.github/workflows/regression-gate.yml) fails; fork PRs never get them.

**CI/CD deploy.** Run `scripts/wizard-setup.sh` to do all the setup below in order; it resumes after an interruption. [`deploy.yml`](.github/workflows/deploy.yml) plans on PRs with a read-only
role; on master it runs the regression gate, waits for approval of the `production`
Environment, applies and smoke-tests the real endpoint. After `scripts/deploy-infra.sh
bootstrap` (it also creates the OIDC roles), set the repository variables `AWS_PLAN_ROLE_ARN`,
`AWS_DEPLOY_ROLE_ARN` (outputs of `infra/bootstrap`), `BUCKET_SUFFIX` and `TF_STATE_BUCKET`,
the secret `ALERT_EMAIL`, and give the `production` Environment required reviewers and master
as its only deployment branch. A failed deploy is not rolled back: run
`gh workflow run deploy.yml --ref master -f sha=<last-good-sha>` or revert on master.

The API key is created by Terraform (read it with `aws apigateway get-api-key --api-key
<api_key_id> --include-value`) and rotated with
`terraform -chdir=infra apply -replace=module.api.aws_api_gateway_api_key.this ...`.

The shared Lambda image measures 947 MB on disk (about 357 MB compressed). Cold start is
about 6.1 s for the first invoke under the Lambda runtime interface emulator and 10-80 ms
warm. These are local docker numbers, not measured on Lambda; details in
[infra/README.md](infra/README.md).

### Deployment

![CI/CD pipeline](docs/diagrams/ci-cd.svg)

The pipeline above is described in the **CI/CD deploy** paragraph of
[Infrastructure](#infrastructure-aws); [ADR 0014](docs/adr/0014-deploy-from-master-with-approval-and-no-auto-rollback.md)
explains why there is no automatic rollback. After the first deploy, run the
[AWS drill](docs/aws-drill.md) and the [runbook](docs/runbook.md) alarm entries as needed.

### Pipeline report (CloudWatch Logs Insights)

`make insights-report` runs 12 Logs Insights queries through boto3 against the API and
worker log groups of the deployed stack and writes `insights-report.md`: jobs by outcome,
duration percentiles, failure reasons, model calls and tokens, repairs and fallbacks,
Grounding Rate, throughput per hour, slowest jobs, Lambda duration, memory and cold starts,
and timeouts. It needs AWS credentials; options are `--hours` (default 24), `--prefix` and
`--output`, e.g. `uv run scripts/insights_report.py --hours 168`. The queries read only the
`job` and `llm_call` wide events, which hold no invoice content, so the report can be shared.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Development workflow

The repository ships with agent skills (`.agents/skills/`, symlinked from `.claude/skills/`),
git hooks, a status line, a knowledge bundle (`.wiki/`, publish it with
`scripts/publish_wiki.sh --push`) and a usage dashboard. Rules are in
[CONTRIBUTING.md](CONTRIBUTING.md) and [CODE_STANDARDS.md](CODE_STANDARDS.md).

### Daily workflow

Everything follows [CONTRIBUTING.md](CONTRIBUTING.md):

```bash
git switch development && git pull
git switch -c feat/my-change
# ... work, then commit as: tag(subject/subsubject): summary
git push -u origin feat/my-change
gh pr create --base development
```

Every commit is checked by the hooks: Unicode, `ruff`, the message format
(English, with `Session-Id` and `Co-Authored-By` trailers) and, when code changed
without `.wiki/`, an automatic wiki update (skip it with `SKIP_WIKI_UPDATE=1`).
To release, open a PR from `development` into `master`.

### Status line budget

The status line shows spend against a USD budget when you pay per token (no
subscription rate limits). The default is `$ 100`; change it with:

```bash
scripts/set-budget.sh 50            # this project only (.claude/budget, git-ignored)
scripts/set-budget.sh 50 --global   # every project (~/.claude/budget)
scripts/set-budget.sh --show        # budget in effect and where it comes from
scripts/set-budget.sh --clear       # remove it (add --global for the global one)
```

It applies on the next refresh, no restart needed. `CLAUDE_BUDGET_USD` overrides
both files. The cost is the estimate reported by Claude Code, not your invoice.

### Usage tracking and report

While the status line runs, it can record one small JSON file per session in
`.claude/usage/` (git-ignored, numbers and metadata only, no conversation
content): the cost **estimate** Claude Code computes, duration, model, effort,
context peak and tokens. It is on by default and per project:

```bash
scripts/usage-tracking.sh status   # on or off
scripts/usage-tracking.sh off      # stop recording (on to resume)
```

`/setup-project-harness` also asks whether to keep it on. Then build the
dashboard with the `usage-report` skill:

```bash
/usage-report                       # this project -> .claude/usage/report.html
/usage-report --all --since 2026-09-01 --top 15 --limit 50
```

It shows tokens in and out per day, session and skill, session duration, model,
effort, context peak, the most used skills, and intents. A **Work** section
follows each feature across sessions (`/to-spec`, `/to-tickets`, `/implement` per
ticket, or `/implement` alone): it links sessions by shared spec, ticket, feature
directory or branch, resolves local `.scratch/` files and GitHub issues (via `gh`,
skipped with `--offline`), and lists the commits carrying the session's
`Session-Id`.

The page has four tabs: Overview, Work, By type (feature, bug fix, refactor... with
the effort each took, from commit tags, branch prefix, GitHub labels or the
opening skill) and Sessions. It also tracks which tools were used (names, calls,
errors and time; no token figures) and shows **subagents as separate rows** nested
under the session that spawned them, never added to that session's numbers.

Read the notice at the top of the page: **cost is an estimate** made by Claude
Code on your machine, not your invoice, and only sessions after tracking was
enabled have one. Tokens per skill are approximate (from the skill call until your
next prompt) and intents are a keyword heuristic. There is no dollar conversion
from tokens and no price table.
<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Roadmap

- [x] Extraction pipeline with anonymization, repair, fallback and escalation
- [x] Local token-free stack, failure-injection suite and `make demo`
- [x] Regression gate with a committed baseline
- [x] Terraform for AWS, deploy workflow with OIDC roles, approval and smoke test
- [ ] Run the [AWS drill](docs/aws-drill.md) and record its outcome
- [ ] Add a `LICENSE`
- [ ] Protect `master` with a branch rule

See the [open issues](https://github.com/emvalencaf/extraction-llm-pipeline/issues) for proposed features and known issues.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Contributing

Contributions follow the branch strategy and commit convention in
[CONTRIBUTING.md](CONTRIBUTING.md):

1. Cut a branch from `development` (`git switch -c feat/my-change`)
2. Commit your changes as `tag(subject/subsubject): summary`, in English, with the
   `Session-Id` and `Co-Authored-By` trailers
3. Push the branch (`git push -u origin feat/my-change`)
4. Open a pull request into `development`

`master` only receives pull requests from `development`. Coding and
documentation rules are in [CODE_STANDARDS.md](CODE_STANDARDS.md).

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## License

No license has been chosen yet. Add a `LICENSE` file before reusing this code.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Contact

Edson Mota Valença Filho - [@emvalencaf](https://github.com/emvalencaf)

Project Link: [https://github.com/emvalencaf/extraction-llm-pipeline](https://github.com/emvalencaf/extraction-llm-pipeline)

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Acknowledgments

* [Best-README-Template](https://github.com/othneildrew/Best-README-Template) for the README structure
* [AWS Architecture Icons](https://aws.amazon.com/architecture/icons/) and [Font Awesome Free](https://fontawesome.com) in the diagrams (see [docs/diagrams/icons/README.md](docs/diagrams/icons/README.md))
* [mattpocock/skills](https://github.com/mattpocock/skills) for the engineering skills
* [scaccogatto/okf-skills](https://github.com/scaccogatto/okf-skills) for the OKF skills
