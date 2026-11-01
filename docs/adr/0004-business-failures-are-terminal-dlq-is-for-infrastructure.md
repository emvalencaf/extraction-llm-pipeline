# Business failures are terminal; the DLQ is for infrastructure only

When validation still fails after repair and escalation, or the PDF has no text
layer, the job ends as `failed_validation` with its reason and best attempt, and
the SQS message is consumed. Only infrastructure failures (all models exhausted,
quota hit, crash) are re-raised, returning the message after the visibility
timeout and moving it to the DLQ after five receives, where the job becomes
`failed`. This keeps the DLQ depth alarm meaningful and makes redrive safe.

## Consequences

A crash on the last receive leaves the job in `processing` with the message in
the DLQ. This known gap is shown on purpose in the failure-injection suite and is
visible through the DLQ depth metric; there is no reconciler.
