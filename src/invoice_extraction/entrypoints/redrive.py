"""Replay the DLQ with native SQS redrive (StartMessageMoveTask), e.g. `make redrive`.

Run it after fixing the cause of an outage. Redriven jobs that the worker marked `failed`
(retries exhausted) are claimed again on delivery; jobs that failed for a business reason
are ignored by the worker.
"""

import os
import sys
import time

import boto3


def _arn(sqs, name: str) -> str:
    url = sqs.get_queue_url(QueueName=name)["QueueUrl"]
    return sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["QueueArn"])["Attributes"][
        "QueueArn"
    ]


def redrive(
    sqs, dlq_name: str = "jobs-dlq", source_name: str = "jobs", wait_seconds: float = 60
) -> dict:
    """Start a native move task DLQ -> source queue and wait for it to finish.

    Return the final task description (Status, ApproximateNumberOfMessagesMoved...).
    """
    dlq_arn = _arn(sqs, dlq_name)
    sqs.start_message_move_task(SourceArn=dlq_arn, DestinationArn=_arn(sqs, source_name))
    deadline = time.monotonic() + wait_seconds
    while True:
        task = sqs.list_message_move_tasks(SourceArn=dlq_arn)["Results"][0]
        if task["Status"] != "RUNNING" or time.monotonic() >= deadline:
            return task
        time.sleep(0.5)


def main() -> int:
    sqs = boto3.client("sqs", endpoint_url=os.environ.get("JOBS_SQS_ENDPOINT_URL"))
    task = redrive(
        sqs,
        os.environ.get("DLQ_NAME", "jobs-dlq"),
        os.environ.get("JOBS_QUEUE_NAME", "jobs"),
    )
    print(f"redrive {task['Status']}: moved {task.get('ApproximateNumberOfMessagesMoved', 0)}")
    return 0 if task["Status"] in {"COMPLETED", "RUNNING"} else 1


if __name__ == "__main__":
    sys.exit(main())
