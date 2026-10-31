# Research: AWS free-tier limits and Lambda packaging for this stack

Issue: #5 (parent map #1). Researched 2026-10-31 from AWS first-party docs and
pricing pages. Each claim cites the page that owns it. "Not verified" marks
things the primary pages did not state.

## 1. Bottom line

- The free-tier model changed for accounts opened on or after 2025-07-15. A new
  account no longer gets "12 months free per service". It gets a **Free plan**
  (credit-based, closes after 6 months) or a **Paid plan** (credits, then pay as
  you go). Plan your budget around credits, not per-service 12-month quotas.
- Everything in the stack (API Gateway, SQS, Lambda, DynamoDB, S3) is usable on
  a new account. Expected cost at hobby scale is cents, covered by credits.
- The Free plan is a **time bomb for a long-lived project**: the account closes
  at 6 months (or when credits run out) unless upgraded to Paid.
- The issue's SQS figure is stale: the SQS max message size is now **1 MiB**,
  not 256 KB.
- LangGraph + google-genai fit a zip (250 MB unzipped cap) if dependencies stay
  lean; otherwise use a container image (10 GB).

## 2. Free-tier rules that apply to new accounts

Source: [Choosing a plan](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier-plans.html),
[AWS Free Tier](https://aws.amazon.com/free/),
[Free Tier terms](https://aws.amazon.com/free/terms/),
[Free Tier FAQ](https://aws.amazon.com/free/faqs/).

| Item | Fact |
|---|---|
| Sign-up credit | USD 100 on sign-up, plus up to USD 100 more for completing activities (up to 200 total), on both plans. |
| Free plan | No charges while on it. Ends after 6 months or when credits are used up, whichever comes first. Limited to a selected set of services (those that could burn credits quickly, e.g. Savings Plans, Reserved Instances, some Marketplace, are excluded). Not eligible for other promotional credits. |
| At Free-plan expiry | Account closes automatically; access to resources lost. AWS retains content 90 days; upgrading to Paid within 90 days restores access and leftover credits apply to future bills. After 90 days the account and resources are permanently deleted. |
| Paid plan | All services; standard pay-as-you-go beyond credits; also gets short-term trials. Account does not close when credits run out. |
| Credit expiry | Terms page: credits expire 12 months after account opening. The FAQ states 6 and 12 months in different answers, so treat it as inconsistent; assume the earlier (6 months) on the Free plan because the plan itself ends then. |
| Always-free | "30+ services" with monthly usage limits on both plans. The pages fetched do not name the services or their limits (the list is rendered client-side), so the exact always-free quotas for Lambda/SQS/DynamoDB/API Gateway are **not verified** from the Free Tier page. Per-service pricing pages are cited below. |
| Auto-upgrade to Paid | Joining AWS Organizations, Control Tower, APN, Professional Services contract, Enterprise Agreement, Skill Builder Team subscription, or HIPAA/SEC designation. |
| Legacy accounts | The 12-month free tier (legacy terms) applies only to customers who already have it. The API Gateway pricing page still lists "up to 12 months" free calls for new customers but says that since 2025-07-15 new customers can instead pick the free plan with up to USD 200 credits. |
| Misc | Offers can be ended at any time; unused usage does not roll over; usage aggregated across the organization and regions. Free-plan accounts are "for evaluation" and not for sensitive data. |

Consequence for this project: an account created today should be treated as a
6-month sandbox. Decide early whether to upgrade to Paid (and set a billing
budget/alarm) before the Free plan lapses.

## 3. Per-service free usage and prices

Prices are US East (N. Virginia) as shown on the pricing pages on the research date.

### Lambda
Source: [Lambda pricing](https://aws.amazon.com/lambda/pricing/)
- Free tier: 1M requests and 400,000 GB-seconds per month. The page does not say
  "always"; it does not apply to Provisioned Concurrency.
- x86: USD 0.20 per 1M requests, USD 0.0000166667 per GB-second. (Arm Event
  Function rates did not extract; check the page before relying on Arm prices.)
- Ephemeral storage: 512 MB free; extra at USD 0.0000000309 per GB-second.
- Init code is billed as duration ("Duration charges apply to code that runs in
  the handler ... as well as initialization code"). So a slow import of
  LangGraph/google-genai costs money on each cold start.

### API Gateway
Source: [API Gateway pricing](https://aws.amazon.com/api-gateway/pricing/)
- Legacy-style free tier for new customers: 1M REST + 1M HTTP calls/month for up
  to 12 months. Since 2025-07-15 new customers can instead take the free plan.
- HTTP API about USD 1.00 per 1M calls; REST API about USD 3.50 per 1M calls
  (tier prices inferred from the page's examples, not a rate table).
- HTTP APIs meter payload in 512 KB increments (a 4.5 MB upload counts as 9
  requests, per the page's example). REST does not state a size increment.
- Data transfer out about USD 0.09 per GB.

### SQS
Source: [SQS pricing](https://aws.amazon.com/sqs/pricing/)
- 1M requests/month free, across all Regions (except GovCloud), no rollover.
- Every 64 KB chunk of a payload bills as one request (a 1 MiB payload = 16
  requests). Up to 10 messages per request, 1 MiB max combined payload.
- Standard-queue per-million rate was not on the extracted page (not verified).

### DynamoDB
Source: [DynamoDB on-demand pricing](https://aws.amazon.com/dynamodb/pricing/on-demand/)
- Free tier: 25 GB storage, 25 WCU + 25 RCU provisioned, 2.5M Streams read
  requests, 1 GB data transfer out; per Region per payer account per month.
  It "uses provisioned capacity and the DynamoDB Standard table class".
- On-demand: USD 0.625 per 1M write request units, USD 0.125 per 1M read request
  units, USD 0.25 per GB-month storage (Standard).
- Cost trap: the request free allowance is tied to **provisioned** capacity.
  On-demand tables appear to be billed for all reads/writes (storage's 25 GB
  does appear to be free in the page's examples). For a tiny workload either is
  pennies, but only provisioned mode uses the request free tier.

### S3 (if needed)
Source: [S3 pricing](https://aws.amazon.com/s3/pricing/)
- New customers: credits (up to USD 200) apply to S3; the page lists no
  specific free-usage quantities for the new model. Free plan lasts 6 months.
- GET USD 0.0004 per 1,000 (S3 Standard, us-east-1). Storage and PUT rates not
  stated on the extracted page (not verified).

## 4. Request and payload limits

| Component | Limit | Source |
|---|---|---|
| API Gateway HTTP API | payload 10 MB; integration timeout 30 s (not adjustable) | [HTTP API quotas](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-quotas.html) |
| API Gateway REST API | payload 10 MB; integration timeout 50 ms - 29 s default; for Regional/private APIs can be raised above 29 s, possibly at the cost of account throttle quota | [REST API quotas](https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-execution-service-limits-table.html) |
| API Gateway account throttle | 10,000 RPS, burst 5,000 (2,500 RPS / 1,250 burst in some newer Regions) | [API Gateway quotas](https://docs.aws.amazon.com/apigateway/latest/developerguide/limits.html) |
| SQS message | **1 MiB max** (1,048,576 bytes); min 1 byte; batch of up to 10 messages; retention default 4 days, max 14; visibility timeout default 30 s, max 12 h; delay up to 15 min | [SQS message quotas](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/quotas-messages.html) |
| SQS larger payloads | Extended Client Library (Java, Python) stores payload in S3, up to 2 GB; sync clients only | same |
| Lambda memory | 128 - 10,240 MB (1,769 MB = 1 vCPU equivalent) | [Lambda quotas](https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html) |
| Lambda timeout | 900 s (15 min) | same |
| Lambda invoke payload | 6 MB sync request and response; 1 MB async | same |
| Lambda /tmp | 512 - 10,240 MB | same |
| Lambda concurrency | default 1,000, but new accounts have reduced concurrency and memory quotas that AWS raises automatically with usage | same |
| Lambda env vars | 4 KB total | same |

Design implications:
- API Gateway (30 s / 29 s) cannot host a long LLM extraction synchronously.
  That is the reason for the async API -> SQS -> Lambda design; the API returns
  a job id and the worker runs up to 15 min.
- A 10 MB API Gateway payload exceeds SQS's 1 MiB and Lambda's 6 MB sync limit.
  Large documents need a presigned S3 upload (S3 in the stack) with only a
  reference in the SQS message.
- The SQS 1 MiB size and the 64 KB billing chunk mean big messages multiply SQS
  request counts against the 1M free requests.
- Lambda's new-account memory quota may cap memory below 10,240 MB at first
  (exact number not stated; check Service Quotas).

## 5. SQS -> Lambda event source mapping

Sources: [Lambda with SQS](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html),
[Configuring an SQS event source mapping](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-configure.html),
[Error handling](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html).

- **Polling/delivery**: Lambda polls the queue and invokes the function
  synchronously with a batch; success deletes the messages. Processing is
  at-least-once, so the handler must be idempotent.
- **Batch size**: default 10; standard queue up to 10,000 (FIFO max 10). Above
  10 you must set a batching window of at least 1 s. The batching window can be
  up to 5 minutes. Total batch payload is capped by the 6 MB sync invoke limit,
  and per-record metadata counts toward it.
- **Visibility timeout**: set to **at least 6x the function timeout** (plus the
  batching window). The function timeout must be <= the queue visibility
  timeout, validated on create/update. With a 15 min Lambda timeout, 6x is 90
  min (under the 12 h SQS maximum), so a failed message can wait up to 90 min
  before retry. Use shorter function timeouts where possible.
- **Partial batch response**: enable `ReportBatchItemFailures` on the mapping and
  return `{"batchItemFailures": [{"itemIdentifier": "<messageId>"}]}`. Empty or
  null list = success. Invalid JSON, empty/null/unknown `itemIdentifier` = whole
  batch fails. An uncaught exception fails the whole batch. With it enabled,
  Lambda does not scale down polling on failures. Powertools batch processor
  (Python) implements this.
- **DLQ/redrive**: configure a DLQ on the **source queue's** redrive policy
  (not on the Lambda). AWS recommends `maxReceiveCount` of **at least 5**.
- **Throttling**: if the function is throttled, Lambda backs off and retries
  until the message's timestamp exceeds the queue's visibility timeout, at which
  point Lambda drops the message (docs wording). Set
  reserved concurrency to at least 5 if you use it to limit scale.
- **Scaling**: starts with 5 concurrent batches, adds up to 300 concurrent
  invokes per minute, to a max of 1,250. Use the mapping's **Maximum
  concurrency** to cap parallelism (protects Gemini quotas and cost).
  Provisioned mode adds cost; not needed here.
- **Permissions**: managed policy `AWSLambdaSQSQueueExecutionRole`; add
  `kms:Decrypt` for encrypted queues.

## 6. Lambda packaging for LangGraph + google-genai

Sources: [Python .zip packaging](https://docs.aws.amazon.com/lambda/latest/dg/python-package.html),
[Lambda quotas](https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html),
[Execution environment lifecycle](https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtime-environment.html).

| Option | Limits | Notes |
|---|---|---|
| Zip | 50 MB zipped via API/console (larger via S3); **250 MB unzipped** including layers and custom runtimes | Simplest. Build wheels for Linux and the target arch: `pip install --platform manylinux2014_x86_64 (or _aarch64) --only-binary=:all: --python-version 3.x --target package`. Exclude `__pycache__`. |
| Layers | max 5 layers; counted in the same 250 MB unzipped total | Only helps reuse/organization; does not raise the cap. Dependencies in the package take precedence over layers. |
| Container image | **10 GB** uncompressed; stored in ECR | Escape hatch if deps exceed 250 MB. ECR storage has its own pricing/quotas (not researched). Cannot convert an existing zip function to image; must create a new function. |

- Package type cannot be changed on an existing function.
- AWS recommends bundling all dependencies, including boto3, to avoid version
  drift with the runtime-provided SDK.
- Python runtime support: docs examples reference Python 3.14.
- Cold start: AWS says typically under 1% of invocations, "under 100 ms to over
  1 second" in general; the largest contributor is init code, which grows with
  package size, imports and layers. The Init phase is limited to 10 s; if it
  does not finish, Lambda retries init inside the first invocation with the
  function timeout. Init is billed. Mitigation: import lazily, import only
  needed submodules, keep dependencies lean. Provisioned Concurrency removes
  cold starts but is paid and outside the free tier. Measured cold start
  numbers for LangGraph/google-genai were not researched (needs a benchmark).
- Not verified: actual installed sizes of `langgraph` and `google-genai`
  (measure in a spike; pydantic, httpx, google-auth are the usual heavy parts).

## 7. Cost traps

1. **Free plan closes the account** at 6 months or credit exhaustion; data is
   deleted after 90 more days unless upgraded.
2. **Auto-upgrade to Paid** if the account joins AWS Organizations, Control
   Tower, etc. (loses free-plan protection).
3. **Credit-based, not quota-based**: usage beyond the always-free limits draws
   down credits; once gone the plan ends.
4. **Provisioned Concurrency** is excluded from the Lambda free tier and bills
   continuously; avoid. SQS Provisioned Mode also adds cost.
5. **DynamoDB on-demand** does not use the 25 WCU/RCU free tier; provisioned
   (Standard table class) does.
6. **SQS billing chunks**: 64 KB per request unit; large messages and long
   polling empty receives inflate counts.
7. **Retries multiply spend**: Lambda is at-least-once, the visibility timeout
   drives redelivery, and `maxReceiveCount` bounds the loop. Each retry re-runs
   a paid LLM call. Use idempotency and a DLQ.
8. **Init time is billed** (heavy imports cost duration on every cold start).
9. **API Gateway REST vs HTTP**: REST is about 3.5x the price of HTTP; HTTP API
   is enough unless REST-only features (API keys/usage plans, WAF) are needed.
10. **Data transfer out** about USD 0.09/GB beyond free allowances.
11. **CloudWatch Logs** ingestion is a common surprise (not researched here).

## 8. Open items (not resolved from primary sources)

- Exact always-free quotas per service on the new model (the Free Tier page
  does not name them in static content).
- Standard-queue SQS price, S3 storage/PUT price, Lambda Arm price.
- New-account Lambda memory/concurrency quota values.
- Cold-start and installed-size numbers for this dependency set (needs a spike).
