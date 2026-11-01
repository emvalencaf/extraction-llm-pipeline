# AWS drill

A human-run exercise on the deployed stack. It proves that the alarms reach your
inbox, that a poison message ends in the DLQ, and that the redrive works. It
complements [runbook.md](runbook.md), which says what to do when each alarm fires
for real.

Run it once after the first deploy and again after any change to the
`observability` or `queue` modules. Record the outcome in [Outcome](#outcome).

The steps below can be run by hand, or in one go with
`scripts/wizard-aws-drill.sh` (it asks you only for what a human must check: the
SNS subscription and the number of emails received).

## Prerequisites

- The stack is up (`scripts/deploy-infra.sh up`, or the `deploy` workflow) and the
  smoke test passed.
- You confirmed the SNS subscription email sent to `alert_email`
  (see "First deploy" in the runbook). Without it, steps 1 and 2 show nothing.
- AWS credentials in the shell, the region set, and the repository checked out
  with its dependencies synced (`uv sync`).

```bash
export AWS_REGION=us-east-1
export PREFIX=invoice-extraction-prod
cd infra
export JOBS_URL=$(terraform output -raw jobs_queue_url)
export DLQ_URL=$(terraform output -raw dlq_url)
cd ..
export JOBS_QUEUE_NAME=${JOBS_URL##*/}
export DLQ_NAME=${DLQ_URL##*/}
```

## 1. Fire every alarm

`set-alarm-state` moves an alarm to `ALARM` without waiting for a real breach. It
exercises the alarm action, the SNS topic and the email. It does not prove the
metric or threshold; step 2 does that for the DLQ.

```bash
for name in job-failed llm-call-errors job-duration-high grounding-rate-low \
            dlq-not-empty queue-age-high worker-errors api-errors; do
  aws cloudwatch set-alarm-state \
    --alarm-name "$PREFIX-$name" \
    --state-value ALARM \
    --state-reason "aws-drill: fire alarm $name"
done
```

Check:

- [ ] One email per alarm arrives within a few minutes (8 in total).
- [ ] Each email names the alarm; its description links the matching runbook
      entry.
- [ ] `aws cloudwatch describe-alarms --alarm-name-prefix $PREFIX --query
      'MetricAlarms[].[AlarmName,StateValue]' --output table` shows all eight in
      `ALARM`, then returning to `OK` or `INSUFFICIENT_DATA` on the next
      evaluation (up to 5 minutes).

## 2. Send a poison message

The worker cannot parse a message whose body is not an S3 notification. It
reports the record as failed, SQS redelivers it, and after `maxReceiveCount` (5)
the message moves to the DLQ. The visibility timeout is 6x the worker timeout
(5400 s), so five receives take hours if you wait. Shorten it for the drill and
restore it at the end.

```bash
aws sqs send-message --queue-url "$JOBS_URL" \
  --message-body 'aws-drill poison message, not an S3 notification'
```

To skip the wait, lower the visibility timeout before sending, and put it back
afterwards (read the original first):

```bash
ORIGINAL=$(aws sqs get-queue-attributes --queue-url "$JOBS_URL" \
  --attribute-names VisibilityTimeout --query Attributes.VisibilityTimeout --output text)
aws sqs set-queue-attributes --queue-url "$JOBS_URL" --attributes VisibilityTimeout=30
# ... send the message, wait for it to reach the DLQ ...
aws sqs set-queue-attributes --queue-url "$JOBS_URL" --attributes VisibilityTimeout="$ORIGINAL"
```

Terraform owns this attribute; `terraform plan` shows the drift if you forget to
restore it.

Check:

- [ ] The worker log group `/aws/lambda/$PREFIX-worker` shows `delivery failed ...
      receive_count=1` up to `5` for the message.
- [ ] The DLQ holds the message:
      `aws sqs get-queue-attributes --queue-url "$DLQ_URL" --attribute-names
      ApproximateNumberOfMessagesVisible`.
- [ ] The `dlq-not-empty` alarm goes to `ALARM` from the real metric and emails
      you (up to 5 minutes after the message lands).
- [ ] The jobs queue is empty again (`ApproximateNumberOfMessagesVisible` and
      `...NotVisible` both 0).

The worker does not raise for a failed record (it returns `batchItemFailures`),
so `worker-errors` stays quiet. That is expected.

## 3. Inspect the DLQ message

```bash
aws sqs receive-message --queue-url "$DLQ_URL" --visibility-timeout 0 \
  --attribute-names All --max-number-of-messages 1
```

- [ ] The body is the poison text sent in step 2.

## 4. Redrive

A poison message fails again after a redrive, so this step shows the mechanics
and the loop. Run it as the runbook says:

```bash
uv run python -m invoice_extraction.entrypoints.redrive
```

- [ ] It prints `redrive COMPLETED: moved 1`.
- [ ] The DLQ is empty and the message is back in the jobs queue, then fails five
      more times and returns to the DLQ (with the shortened visibility timeout,
      within a few minutes).

Then drain it, since the job is not real. Confirm first that the message has no
job to lose, then purge:

```bash
aws sqs purge-queue --queue-url "$DLQ_URL"
```

- [ ] The DLQ is empty and `dlq-not-empty` returns to `OK`.

## 5. Clean up

- [ ] The jobs queue visibility timeout is back to its original value.
- [ ] the jobs queue visibility timeout matches the original (the wizard checks; `scripts/deploy-infra.sh plan` also shows no drift).
- [ ] All alarms are in `OK` or `INSUFFICIENT_DATA`.

## Outcome

Fill this in after you run the drill, one row per run.

| Date | Run by | Commit | Alarms emailed (of 8) | Poison reached the DLQ | Redrive | Notes |
|---|---|---|---|---|---|---|
| 2026-11-01 | Edson Mota Valença Filho | 3a6a2ba | 8 of 8 | yes | ok | Run with `scripts/wizard-aws-drill.sh`. |
