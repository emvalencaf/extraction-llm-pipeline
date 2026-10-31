"""Lambda handler for the worker: SQS events carrying S3 notifications."""

import json
from collections.abc import Callable
from typing import Any
from urllib.parse import unquote_plus

from invoice_extraction.application.jobs import JobService, job_id_from_key

Handler = Callable[[dict[str, Any], Any], dict[str, Any]]


def make_worker_handler(service: JobService) -> Handler:
    def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
        failures = []
        for record in event.get("Records", []):
            try:
                notification = json.loads(record["body"])
                # S3 sends an s3:TestEvent (no Records) when the notification is set up.
                for s3_record in notification.get("Records", []):
                    key = unquote_plus(s3_record["s3"]["object"]["key"])
                    service.process(job_id_from_key(key))
            except Exception:
                failures.append({"itemIdentifier": record["messageId"]})
        return {"batchItemFailures": failures}

    return handler


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda entry point; dependencies are wired from environment variables."""
    from invoice_extraction.composition.runtime import build_job_service

    return make_worker_handler(build_job_service())(event, context)
