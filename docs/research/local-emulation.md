# Research: local emulation of Lambda, S3, SQS, DynamoDB and API Gateway in Docker

Issue: #20 (parent map #1). Researched 2026-10-31 from first-party docs and
repositories (AWS docs, project READMEs, LocalStack docs and blog). Each claim
cites the page that owns it. "Not verified" marks things the primary pages did
not state. Findings only; the decision is left to the author.

## 1. Bottom line

- **Lambda (container image):** the Runtime Interface Emulator (RIE, Apache-2.0)
  is built into the AWS base images and is enough to run the real handler.
  It does **not** emulate event source mappings, orchestration or scaling, so
  the SQS to Lambda poller (batch 1, concurrency 2, partial failures) must be a
  small test harness or come from LocalStack.
- **DynamoDB:** `amazon/dynamodb-local` is the official emulator. Fine for
  conditional writes and the job state model. It ignores provisioned throughput
  and does not reproduce throttling or transaction conflicts.
- **SQS:** two realistic options. ElasticMQ models DLQ (`maxReceiveCount`),
  visibility timeout and, per its issue tracker, StartMessageMoveTask. LocalStack
  SQS lists redrive via message move tasks as implemented. moto does **not**
  implement message move tasks.
- **S3:** **MinIO is no longer a safe default.** Its repository was archived on
  2026-04-25, is "no longer maintained", and ships no pre-built community
  binaries. Candidates that still cover S3 to SQS notifications: LocalStack or
  moto. Garage lacks bucket notifications.
- **API Gateway:** no standalone Docker emulator from AWS. Options are a thin
  shim (a few lines of FastAPI or `sam local start-api`) or LocalStack's API
  Gateway REST support.
- **LocalStack licensing changed:** since 2026-03-23, latest images need an
  account and auth token, including in CI. A Free/Hobby plan exists for
  non-commercial use. Treat it as an optional, token-gated option.
- **Recommendation:** two profiles. A hermetic default (no accounts, no
  tokens) built from DynamoDB Local + moto server (S3 and SQS in one process, so
  notifications work) + RIE container + a ~50-line poller and API shim; and an
  optional LocalStack profile for higher-fidelity runs. Details in section 10.

## 2. Comparison table

| Service | Emulator | Covers | Gaps relevant to this project | Licence / cost |
|---|---|---|---|---|
| Lambda (image) | RIE in AWS base images | Invoke the handler over HTTP | No event source mapping, no concurrency/scaling, no orchestration | Apache-2.0 |
| Lambda + ESM | LocalStack | Lambda, ESM, DynamoDB, SQS, S3, API Gateway REST | Needs auth token (Free/Hobby for non-commercial) | Proprietary plans |
| DynamoDB | DynamoDB Local | Item API, conditional writes (standard API) | No throttling, throughput ignored, no TransactionConflict | Free download |
| SQS | ElasticMQ | DLQ, visibility timeout, FIFO, move/redrive (per issues) | Subset of the API; no S3 notification source | Not stated in README |
| SQS | LocalStack | DLQ, StartMessageMoveTask, visibility | Token-gated | See above |
| SQS + S3 | moto server | SQS, S3 notifications to SQS/Lambda/SNS/EventBridge | No message move tasks; Lambda `PackageType=Image` invoke unsupported | Apache-2.0 |
| S3 | MinIO | S3 API | Repo archived 2026-04-25, source-only | AGPLv3 |
| S3 | Garage | Presigned URLs | No bucket notifications | Not stated on page |
| API Gateway | `sam local start-api` | HTTP server in front of Lambda containers | Not a full API Gateway (no API keys/throttling stated) | AWS SAM CLI |

## 3. Lambda: container-image emulation

Sources: [RIE README](https://github.com/aws/aws-lambda-runtime-interface-emulator),
[Lambda ESM with SQS](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html).

- Run: `docker run -p 9000:8080 <image>`; invoke with
  `POST http://localhost:9000/2015-03-31/functions/function/invocations`.
- Optional env: `AWS_LAMBDA_FUNCTION_TIMEOUT` (seconds) plus
  `AWS_LAMBDA_FUNCTION_VERSION`, `_NAME`, `_MEMORY_SIZE`.
- RIE proxies the Runtime and Extensions APIs and turns HTTP requests into
  events. It does not emulate Lambda orchestration, security/auth or network
  configuration, and X-Ray is unsupported. Linux, x86-64 and arm64 only.
- The README does not say whether RIE serializes invocations. Not verified:
  treat concurrency inside one RIE container as one at a time and run N
  containers (or a pool) to mimic concurrency 2.
- moto states "Invoking a Function with PackageType=Image is not yet supported"
  ([moto Lambda](https://docs.getmoto.org/en/latest/docs/services/lambda.html)),
  so moto cannot be the Lambda for this project's packaging.

## 4. SQS: semantics to reproduce and emulator support

Real semantics (primary):

- Redrive policy carries `maxReceiveCount`: the number of receives before the
  message moves to the DLQ. The DLQ must be in the same account and Region.
  For standard queues the enqueue timestamp is kept when moving to the DLQ, so
  the DLQ retention should exceed the source's
  ([SQS DLQ docs](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html)).
- Event source mapping: Lambda invokes synchronously with a batch; a failed
  batch becomes visible again after the visibility timeout; processing is
  at-least-once so the function must be idempotent; partial batch response
  (batch item failures) avoids retrying successes
  ([Lambda with SQS](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html)).
- Maximum concurrency: per-event-source setting, valid range 2 to 1,000; the
  default mode starts with five concurrent invocations and scales up. It is
  mutually exclusive with provisioned mode
  ([SQS scaling](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-scaling.html)).
  Note for the map: concurrency 2 is the lowest legal value.

Emulator support:

| Capability | ElasticMQ | LocalStack | moto |
|---|---|---|---|
| DLQ with `maxReceiveCount` | Yes, `deadLettersQueue` block, 1 to 1000 ([README](https://github.com/softwaremill/elasticmq)) | Yes, `RedrivePolicy` ([docs](https://docs.localstack.cloud/aws/services/sqs/)) | `list_dead_letter_source_queues` implemented; DLQ behavior not described on the page ([docs](https://docs.getmoto.org/en/latest/docs/services/sqs.html)); not verified |
| Visibility timeout | Yes, default 30 s on auto-created queues | Yes, per-receive override incl. 0 | `change_message_visibility` implemented |
| StartMessageMoveTask (native redrive) | README silent; issues #858 (closed 2024-04-10, "Implement dead-letter queue redrive actions") and #1041 show it exists; #1225 reports a redrive failure on the `-native` GraalVM image, so prefer the JVM image or pin and test ([issues](https://github.com/softwaremill/elasticmq/issues?q=StartMessageMoveTask)) | Start/List/Cancel implemented | **Not implemented** |
| Message persistence | Queue metadata only unless H2 `messages-storage` is enabled | Persistence not on Hobby plan | In-memory |

Failure-injection notes: a message received N times without delete is
dead-lettered in the emulators that implement DLQ, which is what the map's
"5 receives to DLQ" and "worker marks failed on last receive" rely on. The
"growing visibility delay" is plain `ChangeMessageVisibility`, supported in all
three. Real SQS moves a message to the back of the queue after 3 receives when
`maxReceiveCount > 3` (SQS DLQ docs above); no emulator page claims to model
that, so ordering under repeated failure may differ. Not verified.

## 5. S3: presigned uploads and S3 to SQS notifications

- **MinIO:** the repository "was archived by the owner on Apr 25, 2026", is
  marked no longer maintained, remains AGPLv3, and the community edition is
  "source-only" with no pre-compiled binaries; users build their own image
  ([minio/minio](https://github.com/minio/minio)). Do not base the project on it.
- **moto server:** `docker run -p 5000:5000 motoserver/moto:latest`
  ([server mode](https://docs.getmoto.org/en/latest/docs/server_mode.html)).
  Apache-2.0 ([LICENSE](https://github.com/getmoto/moto/blob/master/LICENSE)).
  S3 stores bucket notification configs and sends to Lambda, SNS, SQS and
  EventBridge for Put, Post, Copy, CompleteMultipartUpload and delete events
  ([moto S3](https://docs.getmoto.org/en/latest/docs/services/s3.html)).
  Presigned URL support is not described on that page: not verified, test it.
  Notifications target moto's own SQS, so SQS must be moto too in that profile.
- **LocalStack S3:** presigned URLs are signed client-side; signature and
  expiry validation are off by default (`S3_SKIP_SIGNATURE_VALIDATION=0` to
  enforce); virtual-hosted style is default, path style is the fallback for
  Docker Compose service names; 99 of 116 S3 operations implemented. Presigned
  POST is not covered on the page
  ([docs](https://docs.localstack.cloud/aws/services/s3/)).
  An "expired URL is rejected" test only works with validation on.
- **Garage:** presigned URLs implemented, but `PutBucketNotificationConfiguration`
  is marked missing, so it cannot drive the S3 to SQS step
  ([compat table](https://garagehq.deuxfleurs.fr/documentation/reference-manual/s3-compatibility/)).
- S3 conditional writes (`If-None-Match`): not stated by any page read. Not
  verified; the design does its conditional writes in DynamoDB, so this is moot.

## 6. DynamoDB

Sources: [DynamoDB Local usage notes](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/DynamoDBLocal.UsageNotes.html),
[Docker Hub](https://hub.docker.com/r/amazon/dynamodb-local).

- `docker run -p 8000:8000 amazon/dynamodb-local`; `-inMemory` and `-sharedDb`
  flags; access key id must be letters and digits only (2.0.0 and later).
- Applications "should also work with the DynamoDB web service" except for the
  endpoint, and the notes list no exception for `ConditionExpression` writes.
- Differences that matter for failure injection: provisioned throughput is
  ignored (no throttling exceptions), reads are eventually consistent but look
  strong, `TransactionConflictException` is never thrown (AWS suggests
  mocking it), no PITR, no tagging, table names case-insensitive.
- TTL behavior is not described in the notes: not verified. Do not rely on
  local TTL expiry for the `expired` state; drive it explicitly in tests.
- Licence: the Docker Hub page states none. Not verified.

## 7. API Gateway

- No AWS-provided API Gateway emulator image. `sam local start-api` starts a
  local HTTP server that runs functions in Lambda containers, supports Lambda
  authorizers with an explicit "does not guarantee 100% fidelity" warning, and
  says local testing "doesn't validate everything"
  ([SAM docs](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/using-sam-cli-local-start-api.html)).
  It needs a SAM template, which this Terraform-based project does not have.
- LocalStack lists "API Gateway REST API" on the Hobby plan
  ([licensing](https://docs.localstack.cloud/references/licensing/)).
  Fidelity for API keys and throttling: not verified.
- Practical option: a thin shim (FastAPI or a small HTTP handler) that
  translates `POST /jobs` and `GET /jobs/{id}` to API Gateway proxy events and
  calls RIE. It matches the map's "minimal API key" scope; API Gateway-specific
  behavior (usage plans, 29 s limit, 10 MB cap) is covered by the post-deploy
  smoke test against real AWS, not locally.

## 8. LocalStack licensing and status

- Since **2026-03-23** LocalStack for AWS ships as one image; the latest
  releases require an account and auth token, including CI (use a separate CI
  token as `LOCALSTACK_AUTH_TOKEN`). Community users can pin an older tag (the
  post names 4.12) at the cost of growing drift
  ([announcement](https://blog.localstack.cloud/localstack-single-image-next-steps/),
  [auth token](https://docs.localstack.cloud/aws/getting-started/auth-token/)).
- A **Hobby** plan is the only one offered for non-commercial use. It includes
  S3, SQS, Lambda, DynamoDB and API Gateway REST, with CI testing, but not local
  state persistence or Cloud Pods, and telemetry sharing is enforced
  ([licensing](https://docs.localstack.cloud/references/licensing/)).
- Impact: a public portfolio repo whose CI needs a secret token works against
  the "anyone can replicate" goal from #11 (forks normally do not receive
  repository secrets; general GitHub behavior, not re-verified here).
- Not verified: whether a pinned old community image (4.12) still covers
  message move tasks and ESM.

## 9. Event source mapping reproduction

LocalStack's SQS page does not document ESM (only queue URLs from Lambdas via
`SQS_ENDPOINT_STRATEGY=domain`), so ESM fidelity there is not verified from
that page. For the hermetic profile, reproduce it with a small poller that:

1. Calls `ReceiveMessage` (max 1) honoring the queue visibility timeout.
2. POSTs an SQS-shaped event (`Records[].eventSource: aws:sqs`,
   `attributes.ApproximateReceiveCount`, see the
   [event example](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html))
   to the RIE endpoint.
3. Deletes on success; on error or `batchItemFailures` leaves the message so
   the queue re-delivers and eventually dead-letters it.
4. Runs 2 workers to mirror maximum concurrency 2.

This reproduces failure injection (error, timeout via
`AWS_LAMBDA_FUNCTION_TIMEOUT`, duplicate delivery) but not Lambda's throttling
or scaling ramp-up. Cover those in the post-deploy smoke test.

## 10. Recommendation per service

| Service | Local default | Optional upgrade |
|---|---|---|
| Lambda | RIE via the real container image | LocalStack Lambda |
| SQS + DLQ | moto when S3 notifications must feed it; ElasticMQ (JVM image) for DLQ/redrive tests, with the test sending the S3 event itself | LocalStack SQS |
| S3 | moto server (not MinIO; archived) | LocalStack S3 |
| DynamoDB | DynamoDB Local | LocalStack DynamoDB |
| API Gateway | Thin shim to RIE | LocalStack API Gateway REST |
| ESM | Home-made poller | LocalStack |

Caveat that decides moto vs ElasticMQ: moto has **no StartMessageMoveTask**, so
the native DLQ redrive decided in #10 cannot be exercised on moto; ElasticMQ
or LocalStack can. A workable split is moto for the upload-to-queue path and
ElasticMQ for DLQ/redrive tests. Both work with the same boto3 code through
`AWS_ENDPOINT_URL_*` (moto documents `AWS_ENDPOINT_URL`).

## 11. Open items for the author

1. Is Hobby (non-commercial, token) acceptable for an optional profile, or is
   token-free a hard requirement?
2. Spike to verify: moto S3 presigned PUT plus notification to moto SQS;
   ElasticMQ JVM-image redrive; RIE behavior under two simultaneous invokes.
3. Decide whether API Gateway behavior is checked only by the post-deploy smoke
   test (recommended) or also locally.
