# Local stack from per-service emulators, with a fake Gemini

The local stack uses the Lambda RIE with the real image, DynamoDB Local, a moto
S3 server and ElasticMQ for the queues, with a home-made poller reproducing the
decided SQS contract and a thin FastAPI shim standing in for API Gateway.
LocalStack was left out and MinIO is archived. Code has no `if local` branches,
only endpoint environment variables. Gemini is real by default, and `fake-gemini`
is a local server with a control endpoint that injects 429, 503, timeouts and
bad JSON, which lets CI run the whole failure-injection suite without real calls.

## Consequences

The shim and moto do not reproduce API Gateway throttling or presigned-URL
expiry, so the post-deploy smoke test covers them on AWS.
