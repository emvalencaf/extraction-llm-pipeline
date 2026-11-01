# Native API Gateway key, 403 on a bad key, single-tenant access

The API is a REST API (HTTP APIs have no API keys) with a native key on a usage
plan, so API Gateway rejects bad calls before any Lambda runs: 1 request/s, burst
2 and 100 `POST /jobs` a day, sized for the 500 requests/day Gemini quota. A bad
key returns the native **403**, not a faked 401, and the throttle returns 429.
There is one key and no multi-tenancy: any holder can read any job, protected by
the random UUIDv4 `job_id`. Rotation is manual with
`terraform apply -replace`. These are limitations of a demo, and are stated as
such.
