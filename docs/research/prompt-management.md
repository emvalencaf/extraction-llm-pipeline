# Research: prompt management options and runtime fit

Ticket: [#4](https://github.com/emvalencaf/extraction-llm-pipeline/issues/4) (parent map: #1).
Researched: 2026-10-31. All figures below were read from the primary sources
listed under each claim on that date; re-check before committing to a design.

**Question.** Compare LangSmith Prompt Hub, AWS SSM Parameter Store / AppConfig,
and Git-versioned prompts for this pipeline: free-tier limits,
versioning/tags/rollback, how a Lambda pulls a prompt at runtime (latency,
caching, extra dependency, failure mode), and how a regression gate can pin or
promote a prompt version.

Legend: **[src]** = stated by the cited primary source. **[inf]** = my
inference from sourced facts, not stated by any source. **[gap]** = could not be
confirmed from a primary source.

## Summary

| | LangSmith Prompt Hub | SSM Parameter Store | AWS AppConfig | Git-versioned (in repo) |
|---|---|---|---|---|
| Cost at this scale | $0 (Developer plan) | $0 (standard tier) | Pay per request, no free tier stated | $0 |
| Size cap per prompt | none published [gap] | 4 KB standard / 8 KB advanced | 2 MB hosted (adjustable) | none practical |
| Version identity | commit hash | integer version (last 100 kept) | hosted config version number | commit SHA |
| Movable pointer | tag (one commit per tag) | label (one version per label) | deployment to an environment | branch/tag, or file packaged in artifact |
| Rollback | move tag / env rollback history | move label to older version | redeploy older version; auto-rollback on CloudWatch alarm | revert + redeploy |
| Runtime dependency in Lambda | `langsmith` SDK + API key + egress to LangSmith | Lambda layer (no SDK needed) or boto3 | Lambda layer (AppConfig Agent) | none |
| Runtime failure mode | network call to a third party | AWS-internal call, cached | AWS-internal call, cached | none (bundled) |

## 1. LangSmith Prompt Hub

**Free tier.**
- Developer plan: $0 per seat, max 1 seat, up to 5k base traces per month, base
  trace retention 14 days, community support. "Prompt Hub and Playground" is
  listed as included, with **no numeric limit on prompts, versions or pulls**
  published. [src: https://www.langchain.com/pricing] [gap: prompt/pull quotas]
- Plus is $39/seat/month with 10k base traces. [src: same page]

**Versioning, tags, rollback.**
- Each prompt keeps a commit history; commits can be diffed. [src:
  https://docs.langchain.com/langsmith/manage-prompts]
- A tag references exactly one commit and can be re-pointed to another commit.
  `staging` and `production` are reserved for environments and are set through
  the promotion flow, not the tag picker. Each environment keeps a rollback
  history. [src: same page]
- Pull by tag from code: `client.pull_prompt("name:production")`; by commit:
  `"name:<hash>"`. [src: https://docs.langchain.com/langsmith/manage-prompts-programmatically
  and manage-prompts]
- A single webhook per workspace can fire on prompt commit. [src: manage-prompts]
- [gap] The pages read do not document a programmatic API to move a tag or
  promote to an environment from CI. Verify the SDK/REST surface before relying
  on it for the gate.

**Runtime pull from Lambda.**
- `pip install -U langsmith`, `LANGSMITH_API_KEY`, then `pull_prompt`. Optional
  `include_model=True`. Pulled prompts can be converted to OpenAI/Anthropic
  payloads without LangChain at runtime. [src: manage-prompts-programmatically]
- Built-in cache: process-wide singleton, max size 100, TTL 300 s, 60 s
  background refresh; per-client `disable_prompt_cache=True`, per-call
  `skip_cache=True`; offline mode with `ttl_seconds=None` plus `dump()` /
  `load()` to ship a cache file. [src: same page]
- [inf] The 60 s background refresh is of limited use in Lambda, since the
  execution environment is frozen between invocations; effective refresh is
  TTL-driven on the next call after a thaw.
- [inf] Failure mode: an uncached pull needs egress to a third-party SaaS and a
  secret. On outage, a cold container cannot start unless a `load()`-ed cache
  file is bundled, which would reintroduce a Git-style artifact.
- [gap] No latency figures are published for `pull_prompt`; measure.

## 2. AWS SSM Parameter Store

**Free tier and limits** [src: https://aws.amazon.com/systems-manager/pricing/,
https://docs.aws.amazon.com/general/latest/gr/ssm.html]
- Standard parameters: no additional charge; standard-parameter API
  interactions are free at default throughput. Advanced parameters: $0.05 per
  parameter per month; higher throughput costs $0.05 per 10,000 interactions.
- Value size: 4 KB standard, 8 KB advanced. Parameters: 10,000 standard.
- Versions retained: 100 per parameter.
- `GetParameter` / `GetParameters` / `GetParametersByPath`: 40 TPS default,
  shared across the three. `PutParameter` and `LabelParameterVersion`: 3 TPS
  default.
- [inf] 4 KB is the binding constraint: an extraction prompt with a schema and
  few-shot examples may exceed it. Mitigations: split system/user/schema into
  separate parameters, or use the advanced tier (8 KB, $0.05/month each).
- [gap] The AWS Free Tier page does not name Parameter Store; the free
  statement comes from the pricing page above.

**Versioning, labels, rollback** [src:
https://docs.aws.amazon.com/systems-manager/latest/userguide/sysman-paramstore-labels.html]
- Every change creates a new version.
- Labels: max 10 per version; a label cannot be on two versions of the same
  parameter, but can be moved; cannot be set at parameter creation; max 100
  characters; letters, digits, `.`, `-`, `_`; cannot start with a digit, `aws`
  or `ssm`.
- Reference by `name:version` or `name:label`. A request for a version that does
  not exist fails; it does **not** fall back to latest.
- Rollback = move the label to an earlier version (`label-parameter-version`).
  Labels pin versions against the 100-version window only in the sense that you
  must not let a labelled version age out [inf].

**Runtime pull from Lambda** [src:
https://docs.aws.amazon.com/systems-manager/latest/userguide/ps-integration-lambda-extensions.html]
- Use the AWS Parameters and Secrets Lambda Extension (a layer; no AWS SDK
  required). Local HTTP on port 2773:
  `GET /systemsmanager/parameters/get?name=...&label=...` (or `&version=`; one
  of the two, not both). Requires the `X-Aws-Parameters-Secrets-Token` header
  (the function's session token).
- Cache: `SSM_PARAMETER_STORE_TTL` default 300 s, valid 0 to 300 s; cache size
  default 1000 items. The extension does not detect changes and does not
  auto-refresh before TTL, so a label move takes up to TTL to be seen per
  container.
- `SSM_PARAMETER_STORE_TIMEOUT_MILLIS` defaults to 0 (no timeout); set it
  explicitly.
- IAM: `ssm:GetParameter` (plus `kms:Decrypt` only for SecureString; a prompt
  is not a secret, so use `String`).
- [inf] Failure mode: AWS-internal call, no third-party egress; a cold start
  with SSM unreachable fails unless the code falls back to a bundled default.
- [gap] No published latency figure for a cache hit or miss; measure.

## 3. AWS AppConfig

**Pricing and limits** [src: https://aws.amazon.com/systems-manager/pricing/,
https://docs.aws.amazon.com/general/latest/gr/appconfig.html]
- $0.0000002 per configuration request; $0.0008 per configuration received.
  The pricing page does not state a free allowance. Hosted configuration store
  has no additional cost.
- Hosted configuration size: 2,048 KB default (adjustable). 100 applications,
  100 profiles per application, 20 environments per application.
- [inf] At portfolio volume the cost is cents, but it is the only AWS option
  here that is not plainly free, which matters against a "stay in the free
  tier" goal.

**Versioning and rollout** [src:
https://docs.aws.amazon.com/appconfig/latest/userguide/appconfig-deploying.html,
https://docs.aws.amazon.com/appconfig/latest/userguide/creating-feature-flags-and-configuration-data.html]
- Hosted store versions each configuration; `StartDeployment` takes a
  configuration version, an environment, and a deployment strategy. One
  deployment at a time per environment.
- CloudWatch alarms on an environment can trigger automatic rollback during a
  deployment; a failed distribution is rolled back.
- A freeform profile can also source from SSM Parameter Store or S3.
- [gap] Max retained versions of a hosted configuration was not confirmed.

**Runtime pull from Lambda** [src:
https://docs.aws.amazon.com/appconfig/latest/userguide/appconfig-integration-lambda-extensions-how-it-works.html,
.../appconfig-integration-lambda-extensions-config.html]
- AppConfig Agent Lambda extension (layer) on `localhost:2772`. Polls on
  invocation when the elapsed time exceeds `AWS_APPCONFIG_EXTENSION_POLL_INTERVAL_SECONDS`
  (default 45 s). `..._POLL_TIMEOUT_MILLIS` default 3000 ms: on timeout the
  extension skips the poll and returns previously cached data.
  `..._PREFETCH_LIST` loads configuration before the handler, cutting cold
  start.
- Each Lambda instance has its own cache. Propagation delay = deployment
  strategy time + poll interval.
- AWS states that cold starts that re-fetch frequently raise cost.
- [inf] Best runtime failure behaviour of the three AWS/SaaS options (stale
  cache served on timeout), at the price of the most moving parts (application,
  environment, profile, strategy, deployment in Terraform).

## 4. Git-versioned prompts (files in this repo)

No external source is needed for the mechanics; the points below are [inf] from
the repo's branch strategy (CONTRIBUTING.md) and how Lambda packages code.
- Prompts live as files (for example `prompts/extract_invoice.v1.md`) bundled in
  the Lambda zip. Version identity is the commit SHA; review, diff and rollback
  are PR/revert.
- Runtime: zero network calls, zero extra dependency, no failure mode beyond the
  deploy itself. No size cap beyond Lambda package limits.
- Cost: $0.
- Limit: changing a prompt requires a deploy; no hot swap. For this project that
  is a feature, since the regression gate already runs per PR and a prompt
  change then flows through the same gate and deploy path as code.
- Satisfies the map's "not hard-coded" intent only if prompts are separate
  versioned artifacts loaded by name/version, not string literals.

## 5. How the regression gate pins or promotes a version

| Option | Pin the candidate under test | Promote on pass | Roll back on regression |
|---|---|---|---|
| LangSmith | `pull_prompt("name:<commit-hash>")` in the eval run | move `production` tag (programmatic API [gap]) | move tag back |
| SSM | `name:<version>` in the eval run (fails loudly if absent) | `label-parameter-version --labels live --parameter-version N` | re-label to prior N |
| AppConfig | evaluate the candidate version directly; `StartDeployment` with that version | start a deployment (strategy plus alarms) | redeploy prior version, or alarm auto-rollback |
| Git | the PR's commit SHA; eval reads files from the checkout | merge the PR, deploy | revert commit, redeploy |

[inf] SSM label and Git SHA are the simplest to make deterministic in CI: the
gate evaluates an immutable identifier (version number or SHA), and promotion is
one idempotent call or a merge. Record the evaluated identifier in the
regression report so the report and the deployed prompt are provably the same
artifact.

## Recommendation (for the grilling session, not a decision)

1. **Source of truth: Git.** Prompts as versioned files in the repo, reviewed by
   PR, gated per PR. This is free, dependency-free, and matches the existing
   workflow.
2. **Optional runtime registry: SSM Parameter Store (standard tier, `String`)**
   if hot promotion without redeploy is wanted for the demo: CI writes the
   prompt, the gate evaluates `name:<version>`, promotion moves the `live`
   label, and Lambda reads `name:live` via the Parameters and Secrets
   extension with a short TTL and a bundled-prompt fallback. Watch the 4 KB cap.
3. **LangSmith for tracing, not as the prompt store.** It adds a third-party
   runtime dependency and an unverified promotion API for little gain here.
4. **AppConfig only if** staged rollout with alarm-driven auto-rollback is itself
   a portfolio goal; otherwise it is overbuilt and the only option with
   per-request cost.

Open items to measure or verify before closing the design: 4 KB sufficiency for
the real prompt, cache-hit/miss latency of the chosen path in Lambda, and the
LangSmith programmatic tag/promotion API.

## Sources

- https://www.langchain.com/pricing
- https://docs.langchain.com/langsmith/manage-prompts
- https://docs.langchain.com/langsmith/manage-prompts-programmatically
- https://aws.amazon.com/systems-manager/pricing/
- https://docs.aws.amazon.com/general/latest/gr/ssm.html
- https://docs.aws.amazon.com/general/latest/gr/appconfig.html
- https://docs.aws.amazon.com/systems-manager/latest/userguide/sysman-paramstore-labels.html
- https://docs.aws.amazon.com/systems-manager/latest/userguide/ps-integration-lambda-extensions.html
- https://docs.aws.amazon.com/appconfig/latest/userguide/creating-feature-flags-and-configuration-data.html
- https://docs.aws.amazon.com/appconfig/latest/userguide/appconfig-deploying.html
- https://docs.aws.amazon.com/appconfig/latest/userguide/appconfig-integration-lambda-extensions-how-it-works.html
- https://docs.aws.amazon.com/appconfig/latest/userguide/appconfig-integration-lambda-extensions-config.html
