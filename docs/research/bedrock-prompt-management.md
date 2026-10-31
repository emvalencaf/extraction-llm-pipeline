# Research: AWS Bedrock Prompt Management as a prompt store

Ticket: [#15](https://github.com/emvalencaf/extraction-llm-pipeline/issues/15) (parent map: #1).
Extends [prompt-management.md](prompt-management.md) (ticket #4), same criteria.
Researched: 2026-10-31. Figures were read from the cited primary sources on that
date; re-check before committing to a design.

**Question.** Is Bedrock Prompt Management a viable prompt store for a Lambda
pipeline whose model is Gemini (not Bedrock)? Cost and free-tier/credit fit,
regions, versioning and rollback, fetching prompts without invoking Bedrock
models, Lambda runtime pull, template syntax and limits, Terraform, regression
gate pin/promote.

Legend: **[src]** stated by the cited primary source. **[inf]** my inference.
**[gap]** not confirmed from a primary source.

## Summary

| | Bedrock Prompt Management | SSM Parameter Store (from #4) | Git (from #4) |
|---|---|---|---|
| Cost | No separate charge found; model inference billed; optimizer is paid | $0 standard tier | $0 |
| Size cap | none published [gap] | 4 KB / 8 KB | none practical |
| Version identity | integer 1..N, immutable snapshot [inf immutable] | integer, last 100 | commit SHA |
| Versions kept | **10 per prompt, not adjustable** | 100 | unlimited |
| Movable pointer (alias/label) | **none documented** | label | branch/tag |
| Fetch without a Bedrock model | yes, `GetPrompt` (control plane) | yes | yes |
| Lambda read | `bedrock-agent` `GetPrompt`, 10 TPS, no extension/cache | extension, cached | bundled |
| Terraform | prompt resource yes; version resource not confirmed [gap] | yes | n/a |

## 1. Cost and free-tier / credit fit

- Bedrock pricing page lists no separate charge for Prompt Management. The only
  Prompt-Management-related item is the Simple Prompt Optimizer at $0.03 per
  1,000 tokens (input plus optimized output); the Advanced optimizer bills
  on-demand token rates. [src: https://aws.amazon.com/bedrock/pricing/] Only the
  first 100,000 of 118,308 characters of that page were read; the rest was not
  checked [gap].
- [inf] Storing and fetching prompts therefore appears to cost nothing beyond
  the Free plan's credit usage; running inference on a Bedrock model would be
  billed, but we use Gemini, so only the store is relevant.
- New credit-based plans: new accounts get USD 100 in credits, plus up to USD
  100 more for completing activities. The **Free account plan** ends after six
  months or when credits are used, whichever is first; the account then closes
  automatically, content is retained 90 days, and upgrading to a Paid plan within
  90 days keeps it (remaining credits apply to future bills). It includes only
  "select" services; services that could deplete credits are excluded.
  [src: https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier-plans.html]
- Bedrock is listed as "Available on both plans" (Free and Paid); Bedrock
  AgentCore is "Paid plan exclusive". [src: https://aws.amazon.com/free/] The
  Free Tier FAQ was not retrievable, so any Bedrock-specific credit rule (for
  example third-party model restrictions) is [gap]. Prompt Management itself is
  not called out separately [gap].
- [inf] Practical consequence: on the Free plan this is credit-funded, not
  "free forever". The six-month account closure is the real constraint for a
  portfolio project that must stay alive; SSM standard parameters and Git do
  not carry this cliff beyond the account itself. Upgrading to Paid removes it
  but ends the "no charges" guarantee.

## 2. Regional availability

- Supported Regions (22): ap-northeast-1/2/3, ap-south-1/2, ap-southeast-1/2,
  ca-central-1, eu-central-1/2, eu-north-1, eu-south-1/2, eu-west-1/2/3,
  sa-east-1, us-east-1, us-east-2, us-gov-east-1, us-gov-west-1, us-west-2.
  [src: https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-management-supported.html]
- The API endpoint is the build-time Agents endpoint
  `bedrock-agent.<region>.amazonaws.com`. [src:
  https://docs.aws.amazon.com/general/latest/gr/bedrock.html] That page lists 13
  endpoint Regions, fewer than the 22 above; the discrepancy is unresolved [gap].
- [inf] The prompt lives in one Region; the Lambda must call that Region.

## 3. Versioning, aliases, rollback

- Saving creates/updates a mutable `DRAFT`. `CreatePromptVersion` takes a
  snapshot; "versions are created incrementally, starting from 1".
  [src: .../prompt-management-deploy.html, .../prompt-management-version-create.html]
- **Quota: 10 versions per prompt, not adjustable.** 500 prompts per account
  (adjustable). [src: https://docs.aws.amazon.com/general/latest/gr/bedrock.html]
  Versions can be deleted. [src: prompt-management-deploy.html topic list]
- **No alias or label concept was found** in the Prompt Management docs; the
  deploy page only describes draft and numbered versions. The Bedrock "alias"
  feature belongs to Agents. [gap: absence of evidence; verify]
- Version identifiers match `DRAFT|[1-99999]`. [src: GetPrompt API reference]
- [inf] With no movable pointer, "live" is whatever version number the caller
  asks for. Promotion and rollback = change a number held elsewhere (env var,
  SSM parameter, Terraform variable). The 10-version cap forces pruning, so
  the previous known-good version must not be deleted.
- [inf] Immutability of numbered versions is implied by "snapshot", but the pages
  read do not state it outright [gap].

## 4. Fetching without invoking a Bedrock model

- `GetPrompt` (`bedrock-agent`) returns the prompt definition; it needs no model
  call. `GET /prompts/{promptIdentifier}?promptVersion=N`, omit the version for
  `DRAFT`; `includedData=METADATA_ONLY` is available. The identifier is the
  10-char ID or the prompt ARN. [src:
  https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent_GetPrompt.html]
- The response carries `variants[].templateConfiguration` (the text or chat
  template), `modelId`, `inferenceConfiguration`, `version`, `arn`. [src: same]
  The variant's `modelId` is only required by Prompt Management unless an agent
  resource is set (Terraform docs); a Bedrock model id must therefore be stored
  even if unused [inf, from: Terraform `model_id` "required unless
  gen_ai_resource set"].
- Alternative runtime path: `Converse` with the prompt version ARN as `modelId`
  and `promptVariables` renders and runs it, but that invokes a Bedrock model
  and forbids `system`, `inferenceConfig`, `toolConfig`,
  `additionalModelRequestFields` in the request. [src: API_runtime_Converse.html]
  Not usable with Gemini. `InvokeModel` only works for Anthropic Claude or Meta
  Llama prompts. [src: prompt-management-supported.html]
- [inf] For Gemini we must call `GetPrompt` and perform `{{variable}}`
  substitution ourselves. There is a `bedrock:RenderPrompt` IAM action
  (listed in prereqs), but no documented standalone Render API was read [gap].

## 5. Lambda runtime pull

- boto3 client `bedrock-agent`, `get_prompt(promptIdentifier=..., promptVersion="N")`.
  [src: bedrock.html example]
- IAM: `bedrock:GetPrompt`. The AWS sample policy uses `Resource: "*"`; the
  Service Authorization Reference allows scoping to prompt resources (not
  opened) [gap]. A customer-managed KMS key adds `kms:Decrypt`/`GenerateDataKey`;
  default is an AWS managed key. [src: prompt-management-prereq.html]
- Limit: GetPrompt 10 requests per second, not adjustable; throttled calls
  should be retried with backoff. [src: bedrock.html]
- No Lambda extension, no built-in cache, no TTL (contrast with SSM Parameters
  extension and AppConfig Agent in #4). [inf: none documented] Cache must be
  hand-written: fetch once per container at init and hold in memory; a pinned
  numbered version never changes, so caching it forever is safe.
- Failure mode: regional AWS call on cold start; fall back to a bundled prompt
  if throttled/unreachable. [inf]
- Latency: not published [gap]; measure.

## 6. Template syntax and limits

- Variables: double curly braces, `{{variable}}`. [src:
  API_agent_TextPromptTemplateConfiguration.html]
- Template types: `TEXT` (single string, min length 1) or `CHAT` (system +
  message list, tools, cache points). `CHAT` needs a Converse-capable model and
  is required for prompt caching. [src: prompt-management-create.html]
- `inputVariables`: max 20 per template. [src: TextPromptTemplateConfiguration]
- Description max 200 chars; name pattern `([0-9a-zA-Z][_-]?){1,100}`.
  [src: GetPrompt]
- `GetPrompt` response `variants` array holds at most 1 item; the console allows
  comparing up to 3 variants while editing, and "save as draft" discards the
  rest. [src: GetPrompt; prompt-management-create.html]
- **Maximum prompt text size: not published** in the pages read; the 4 KB figure
  on the quotas page applies to model-evaluation datasets, not here. [gap]
- Variable values are only text/structured via `promptVariables` in Converse;
  for our path the variables are substituted client side, so no extra limits
  apply. [inf]

## 7. Terraform

- `aws_bedrockagent_prompt` exists in the AWS provider docs: `name`,
  `default_variant`, `customer_encryption_key_arn`, `variant` blocks
  (`template_type` TEXT/CHAT, `model_id`, `inference_configuration`,
  `template_configuration` with `text`/`chat`, `input_variable`), exports `arn`,
  `id`, `version`. "When you create a prompt, the version created is the
  `DRAFT` version." [src: hashicorp/terraform-provider-aws docs,
  r/bedrockagent_prompt]
- A resource to **create numbered versions** was not found in the page read and
  not searched further. [gap] Without it, versions need the API/CLI
  (`create-prompt-version`) from CI or a `terraform_data` local-exec. [inf]
- [inf] Terraform is a poor fit for the prompt body itself: each prompt edit is
  an infra change, and Terraform manages the DRAFT, not a pinned version.

## 8. How the regression gate pins or promotes a version

| Step | Mechanism |
|---|---|
| Candidate under test | `create-prompt-version` from DRAFT in CI; evaluate `get_prompt(..., promptVersion=N)` |
| Record identity | store `arn` + `version` N in the regression report |
| Promote on pass | no alias: write N to an external pointer (SSM parameter, Lambda env var via Terraform) |
| Roll back | repoint to previous N (must still exist: 10-version cap) |

[inf] Everything above except `get_prompt` and `create-prompt-version` is
built outside Bedrock, so Bedrock replaces only the "store" role and still needs
SSM or Terraform to carry the "live" pointer.

## Comparison with #4 options (inference)

- vs SSM: SSM gives labels (rollback = move a label), 100 versions, a cached
  Lambda extension, no per-account credit cliff. Bedrock gives a console
  prompt builder, variable declarations and per-variant model config, none of
  which Gemini can use directly.
- vs Git: Git is still the only option where the gate, the review and the
  deploy share one identifier with no runtime dependency.
- Bedrock adds a Region-bound regional dependency, a Free-plan expiry cliff, a
  hard 10-version ceiling and no alias, in exchange for a UI this project does
  not need.

## Recommendation (for the grilling session, not a decision)

1. Do not adopt Bedrock Prompt Management as the prompt store. Its value is
   tied to invoking Bedrock models; with Gemini it reduces to a numbered
   key-value store with a 10-version cap and no alias.
2. Keep the #4 recommendation: Git as source of truth, optional SSM labels for
   hot promotion.
3. Reconsider only if the model provider moves to Bedrock, or the console
   prompt builder and variant A/B comparison become a stated goal.

Open items: confirm Free Tier FAQ treatment of Bedrock; max prompt text size
(Service Quotas console); alias absence; Terraform version resource; GetPrompt
latency; region list discrepancy (22 vs 13).

## Sources

- https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-management.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-management-supported.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-management-create.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-management-deploy.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-management-version-create.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-management-prereq.html
- https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent_GetPrompt.html
- https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent_TextPromptTemplateConfiguration.html
- https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html
- https://docs.aws.amazon.com/general/latest/gr/bedrock.html
- https://aws.amazon.com/bedrock/pricing/
- https://aws.amazon.com/free/
- https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier-plans.html
- https://github.com/hashicorp/terraform-provider-aws (docs r/bedrockagent_prompt)
