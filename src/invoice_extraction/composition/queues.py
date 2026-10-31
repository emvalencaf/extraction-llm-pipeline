"""Queue names and URLs shared by the worker wiring and the local-stack tools."""

import os

DEFAULT_JOBS_QUEUE = "jobs"


def jobs_queue_name() -> str:
    return os.environ.get("JOBS_QUEUE_NAME", DEFAULT_JOBS_QUEUE)


def queue_url(sqs, name: str) -> str:
    return sqs.get_queue_url(QueueName=name)["QueueUrl"]


def jobs_queue_url(sqs) -> str:
    """JOBS_QUEUE_URL when set, else the URL of the queue named by JOBS_QUEUE_NAME."""
    return os.environ.get("JOBS_QUEUE_URL") or queue_url(sqs, jobs_queue_name())
