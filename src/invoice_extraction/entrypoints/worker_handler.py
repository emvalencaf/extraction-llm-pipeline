"""Lambda handler for the worker: SQS events carrying S3 notifications.

Batch size is 1. A failed record is reported in `batchItemFailures`; for a transient
infrastructure failure the message is first hidden for a growing visibility delay.
"""

import json
import logging
from collections.abc import Callable
from functools import cache
from typing import Any
from urllib.parse import unquote_plus

from invoice_extraction.application.jobs import JobService, RetryLaterError, job_id_from_key
from invoice_extraction.application.ports import QueueDelayer

logger = logging.getLogger(__name__)

Handler = Callable[[dict[str, Any], Any], dict[str, Any]]


def _receive_count(record: dict[str, Any]) -> int:
    """How many times SQS has delivered this message (1 when the attribute is absent)."""
    return int(record.get("attributes", {}).get("ApproximateReceiveCount", 1))


def _object_key(s3_record: dict[str, Any]) -> str:
    """The uploaded object's key from an S3 notification record (URL-encoded there)."""
    return unquote_plus(s3_record["s3"]["object"]["key"])


def make_worker_handler(
    service: JobService,
    # Optional: in-process tests drive the handler without a queue, and a record without a
    # receiptHandle has nothing to delay.
    delayer: QueueDelayer | None = None,
) -> Handler:
    def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
        failures = []
        for record in event.get("Records", []):
            receive_count = _receive_count(record)
            try:
                notification = json.loads(record["body"])
                # S3 sends an s3:TestEvent (no Records) when the notification is set up.
                for s3_record in notification.get("Records", []):
                    service.process(job_id_from_key(_object_key(s3_record)), receive_count)
            except RetryLaterError as retry:
                if delayer is not None and "receiptHandle" in record:
                    try:
                        delayer.delay(record["receiptHandle"], retry.delay)
                    except Exception as error:  # the default visibility timeout still applies
                        logger.warning(
                            "could not delay message message_id=%s error=%s",
                            record["messageId"],
                            type(error).__name__,
                        )
                failures.append({"itemIdentifier": record["messageId"]})
            except Exception as error:
                logger.error(
                    "delivery failed message_id=%s receive_count=%s error=%s",
                    record["messageId"],
                    receive_count,
                    type(error).__name__,
                )
                failures.append({"itemIdentifier": record["messageId"]})
        return {"batchItemFailures": failures}

    return handler


@cache
def _handler() -> Handler:
    """Wired once per process: building the pipeline (Presidio, spaCy) is slow."""
    from invoice_extraction.composition.runtime import build_job_service, build_queue_delayer

    return make_worker_handler(build_job_service(), build_queue_delayer())


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda entry point; dependencies are wired from environment variables."""
    return _handler()(event, context)
