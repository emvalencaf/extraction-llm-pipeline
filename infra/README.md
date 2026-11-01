# Infrastructure

Terraform for the `prod` environment in `us-east-1`; usage is in the Infrastructure
section of the [root README](../README.md#infrastructure-aws).

## Lambda image: size and cold start

One image serves both functions (the API handler and the worker). Measured locally with
docker on 2026-10-31, **not on Lambda**:

| Measure | Value |
|---|---|
| Size on disk | 947 MB |
| Compressed (what ECR stores and Lambda pulls) | about 357 MB |
| First invoke under the Lambda runtime interface emulator (cold start) | 6.07 s |
| Warm invokes | 10-80 ms |

The cold start is dominated by building the service with Presidio and spaCy. Real Lambda
cold starts also include the image pull and will differ; re-measure after deploying.

## API throttling

POST `/jobs` (1 rps, burst 2) and GET `/jobs/{job_id}` (20 rps, burst 40) are throttled
per method in the usage plan (`api_stages.throttle`). The plan-level throttle is only the
ceiling, set to the larger of the two, because it caps every method.
