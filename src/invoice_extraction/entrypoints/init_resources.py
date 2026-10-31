"""Create the local stack's AWS resources with boto3 (S3, DynamoDB, queues, notification).

Idempotent. Resource names come from `RESOURCES` and are checked against the Terraform
definitions by `check_against_terraform`: `infra/locals.tf` holds the same logical names, and
Terraform prefixes them (`invoice-extraction-prod-<name>`).
"""

import json
import os
from pathlib import Path

import boto3

RESOURCES = {
    "bucket": "invoices",
    "table": "jobs",
    "jobs_queue": "jobs",
    "jobs_dlq": "jobs-dlq",
    "s3_events_queue": "s3-events",
}
MAX_RECEIVES = 5  # receives before the DLQ; the worker marks the job failed on the 5th


# Only the local stack has it: on AWS, S3 notifies the jobs queue directly (no relay needed).
LOCAL_ONLY = frozenset({"s3_events_queue"})


def check_against_terraform(root: Path = Path("infra")) -> str:
    """Return a status line; raise if a local resource name is missing from the .tf files."""
    if not root.is_dir():
        return f"terraform check skipped: no {root} directory"
    text = "\n".join(path.read_text() for path in root.rglob("*.tf"))
    missing = [
        f"{k}={v}" for k, v in RESOURCES.items() if k not in LOCAL_ONLY and f'"{v}"' not in text
    ]
    if missing:
        raise SystemExit(f"resources missing from Terraform: {', '.join(missing)}")
    return "terraform check passed"


def init(s3, dynamodb, jobs_sqs, events_sqs) -> None:
    names = RESOURCES
    existing = {b["Name"] for b in s3.list_buckets()["Buckets"]}
    if names["bucket"] not in existing:
        s3.create_bucket(Bucket=names["bucket"])

    if names["table"] not in dynamodb.list_tables()["TableNames"]:
        dynamodb.create_table(
            TableName=names["table"],
            KeySchema=[{"AttributeName": "job_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "job_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

    dlq_url = jobs_sqs.create_queue(QueueName=names["jobs_dlq"])["QueueUrl"]
    dlq_arn = jobs_sqs.get_queue_attributes(QueueUrl=dlq_url, AttributeNames=["QueueArn"])[
        "Attributes"
    ]["QueueArn"]
    jobs_sqs.create_queue(
        QueueName=names["jobs_queue"],
        Attributes={
            "VisibilityTimeout": os.environ.get("VISIBILITY_TIMEOUT", "60"),
            "RedrivePolicy": json.dumps(
                {"deadLetterTargetArn": dlq_arn, "maxReceiveCount": MAX_RECEIVES}
            ),
        },
    )

    events_url = events_sqs.create_queue(QueueName=names["s3_events_queue"])["QueueUrl"]
    events_arn = events_sqs.get_queue_attributes(QueueUrl=events_url, AttributeNames=["QueueArn"])[
        "Attributes"
    ]["QueueArn"]
    s3.put_bucket_notification_configuration(
        Bucket=names["bucket"],
        NotificationConfiguration={
            "QueueConfigurations": [
                {
                    "QueueArn": events_arn,
                    "Events": ["s3:ObjectCreated:*"],
                    "Filter": {"Key": {"FilterRules": [{"Name": "prefix", "Value": "uploads/"}]}},
                }
            ]
        },
    )


def main() -> None:
    print(check_against_terraform(), flush=True)
    init(
        s3=boto3.client("s3"),
        dynamodb=boto3.client("dynamodb"),
        jobs_sqs=boto3.client("sqs", endpoint_url=os.environ.get("JOBS_SQS_ENDPOINT_URL")),
        events_sqs=boto3.client("sqs", endpoint_url=os.environ.get("S3_EVENTS_SQS_ENDPOINT_URL")),
    )
    print("init done", flush=True)


if __name__ == "__main__":
    main()
