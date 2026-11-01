# Wide events with embedded metrics; no LangSmith

Observability is two JSON wide events joined by `job_id` (`llm_call` and `job`),
with CloudWatch metrics embedded as EMF rather than metric filters or
`PutMetricData`, and no extra dimensions so the metrics stay inside the 10 free
custom metrics. Invoice text, placeholders and extracted values are never logged.
LangSmith was rejected: wide events cover the need, and it would add a runtime
SDK, egress, a secret and third-party exposure of invoice content.
