# Runbook

One entry per CloudWatch alarm of the `observability` module
(`infra/modules/observability`). Every alarm publishes to the single SNS
`alerts` topic, which emails the address given as `alert_email`. The cost budget
publishes to the same topic. Alarm names are `invoice-extraction-prod-<name>`;
the headings below are the `<name>`.

Application metrics are EMF in the `InvoiceExtraction` namespace, with no
dimensions. Wide events (`llm_call`, `job`) are in the log group
`/aws/lambda/invoice-extraction-prod-worker`. Open the
`invoice-extraction-prod-overview` dashboard first. Missing data never breaches
an alarm, so silence means no traffic, not health.

Find a job in the logs with CloudWatch Logs Insights:

```text
fields @timestamp, event, job_id, outcome, reason, model
| filter job_id = "<job id>"
| sort @timestamp asc
```

## `job-failed`

- **Fires when:** `JobInfraFailed` sums above 0 in 5 minutes. A job ended
  `failed`, `unavailable` or `error`: an infrastructure or model outage, not a
  bad document. A `failed_validation` does not page; it counts in `JobFailed`
  on the dashboard only.
- **Check:** the `job` events with `outcome` other than `succeeded` and
  `failed_validation`; `reason` tells which error stopped it (retries
  exhausted, model unavailable).
- **Act:** `retries_exhausted` and `unavailable` mean infrastructure or Gemini
  trouble: see `dlq-not-empty` and `llm-call-errors`. For a burst of
  `failed_validation` after a deploy (visible on the dashboard), suspect a
  prompt or schema regression: revert the change and run the regression gate.

## `llm-call-errors`

- **Fires when:** `LlmCallError` sums to 5 or more in 5 minutes (calls with
  outcome `transient_error` or `rejected`).
- **Check:** the `llm_call` events by `model`, `tier` and `outcome`. Many
  `transient_error` from one model means Gemini 429/503 (free-tier quota or
  outage); `rejected` means replies failing validation.
- **Act:** for quota, wait: the graph retries with jitter, SQS delays by a
  growing visibility timeout, and the fallback model takes over. If it persists,
  check the Gemini key in SSM and the quota in Google AI Studio. For `rejected`,
  see `job-failed`.

## `job-duration-high`

- **Fires when:** the longest `JobDurationMs` exceeds 80% of the worker timeout
  (720 s of 900 s).
- **Check:** `llm_calls`, `repairs`, `escalated` and `fell_back` on the slow
  `job` events, and `LlmLatencyMs` on the dashboard.
- **Act:** a job near the timeout risks a hard Lambda timeout, which leaves the
  job `processing`. Slow Gemini: wait or lower the attempts. Many repairs: a
  prompt problem. If it recurs, raise `worker_timeout_seconds` (the queue
  visibility timeout follows at 6x).

## `grounding-rate-low`

- **Fires when:** the average `GroundingRate` is below 0.8 over one hour. The
  rate is informational per job, so this flags a drift in extraction quality,
  not a failed job.
- **Check:** `grounding_rate` on `job` events and the prompt version in the same
  events.
- **Act:** if it started with a deploy, compare against the last regression-gate
  report and revert the prompt or model change. If not, the incoming documents
  changed (new template): sample a few results by hand.

## `dlq-not-empty`

- **Fires when:** at least one message is visible in the DLQ. The DLQ holds
  infrastructure failures only; the worker already marks a job `failed` on the
  last receive.
- **Check:** the worker logs for the message's `job_id` and the cause (Lambda
  timeout, throttling, crash). Inspect the message in the SQS console.
- **Act:** fix the cause, then replay with the native DLQ redrive (`make
  redrive` on the local stack; against AWS run `python -m
  invoice_extraction.entrypoints.redrive` with AWS credentials, `DLQ_NAME` and
  `JOBS_QUEUE_NAME` set). A poison message that keeps failing can be purged
  after confirming the job is already terminal.

## `queue-age-high`

- **Fires when:** the oldest message in the jobs queue is older than 900 s for
  10 minutes.
- **Check:** `ApproximateAgeOfOldestMessage` and the worker's `Errors` and
  throttles. Backoff after quota errors raises the age on purpose, so look at
  `llm-call-errors` first.
- **Act:** a stuck or crashing worker: fix and redeploy. A quota outage: wait. A
  backlog larger than usual: concurrency is capped at 2 to stay inside Gemini's
  free tier, so do not raise it.

## `worker-errors`

- **Fires when:** the worker Lambda reports any `Errors` in 5 minutes (exception
  or timeout).
- **Check:** the worker log group for the stack trace. Common causes: image or
  dependency failure at cold start, a missing or invalid Gemini parameter in
  SSM, a timeout.
- **Act:** a deploy introduced it: revert or dispatch the previous commit SHA
  (there is no auto-rollback). A missing parameter: set the SecureString named
  by the `gemini_parameter_name` output. Failed messages return to the queue and
  end in the DLQ after 5 receives.

## `api-errors`

- **Fires when:** the API Lambda reports any `Errors` in 5 minutes. Throttling
  (429) and bad keys (403) are answered by API Gateway and do not count here.
- **Check:** the API log group `/aws/lambda/invoice-extraction-prod-api` for the
  stack trace.
- **Act:** as `worker-errors`: revert or dispatch the previous SHA. Run the
  smoke test against the endpoint to confirm recovery.

## Budget notice

The `invoice-extraction-prod-monthly` budget (USD 10, resources tagged
`Project`) emails at 80% actual and at 100% forecast. It is not an alarm. Check
Cost Explorer filtered by the `Project` tag. The tag must be activated as a cost
allocation tag in Billing, and takes up to 24 hours to show costs. If a runaway
cost is real, throttle the usage plan or run `scripts/deploy-infra.sh down`.

## First deploy

AWS emails a subscription confirmation to `alert_email`; alarms do not reach you
until you click it.
