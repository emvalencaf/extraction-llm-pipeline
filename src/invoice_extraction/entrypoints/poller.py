"""Local stand-in for S3 -> SQS -> Lambda event source mapping.

Relay: moto S3 publishes notifications to a moto SQS queue; the relay copies them to the
ElasticMQ jobs queue (skipping the s3:TestEvent). Workers: each worker long-polls the jobs
queue and invokes its own RIE container, because RIE cannot take simultaneous invokes.
"""

import json
import logging
import os
import threading
import time
import urllib.request
from collections.abc import Callable
from typing import Any

import boto3

from invoice_extraction.composition.queues import jobs_queue_name, queue_url

logger = logging.getLogger(__name__)

Invoke = Callable[[dict[str, Any]], dict[str, Any]]


def relay_once(source, source_url: str, dest, dest_url: str) -> bool:
    """Move one S3 notification between queues. Return False when the source is empty."""
    messages = source.receive_message(QueueUrl=source_url, MaxNumberOfMessages=1).get("Messages")
    if not messages:
        return False
    message = messages[0]
    if "Records" in json.loads(message["Body"]):
        dest.send_message(QueueUrl=dest_url, MessageBody=message["Body"])
    source.delete_message(QueueUrl=source_url, ReceiptHandle=message["ReceiptHandle"])
    return True


def work_once(sqs, queue_url: str, invoke: Invoke, wait_seconds: int = 0) -> bool:
    """Deliver one message to a Lambda as an SQS event. Return False when none was waiting.

    Success deletes the message. A reported failure or a crash leaves it for redelivery
    after the visibility timeout, as the real event source mapping does.
    """
    messages = sqs.receive_message(
        QueueUrl=queue_url,
        MaxNumberOfMessages=1,
        WaitTimeSeconds=wait_seconds,
        AttributeNames=["ApproximateReceiveCount"],
    ).get("Messages")
    if not messages:
        return False
    message = messages[0]
    event = {
        "Records": [
            {
                "messageId": message["MessageId"],
                "receiptHandle": message["ReceiptHandle"],
                "body": message["Body"],
                "attributes": {
                    "ApproximateReceiveCount": message["Attributes"]["ApproximateReceiveCount"]
                },
                "eventSource": "aws:sqs",
            }
        ]
    }
    try:
        result = invoke(event)
    except Exception as error:
        logger.warning(
            "invoke failed, message left for redelivery message_id=%s error=%s",
            message["MessageId"],
            type(error).__name__,
        )
        return True
    if not result.get("batchItemFailures"):
        sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=message["ReceiptHandle"])
    return True


def rie_invoker(url: str) -> Invoke:
    def invoke(event: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(url, data=json.dumps(event).encode(), method="POST")
        with urllib.request.urlopen(request, timeout=900) as response:
            return json.loads(response.read())

    return invoke


def _forever(step: Callable[[], bool], idle: float = 0.5) -> None:
    while True:
        try:
            if not step():
                time.sleep(idle)
        except Exception as error:  # keep the loop alive while dependencies start up
            logger.warning("poller step failed error=%s", type(error).__name__)
            time.sleep(1)


def _queue_url(sqs, name: str) -> str:
    """Wait for `init` to create the queue, then return its URL."""
    while True:
        try:
            return queue_url(sqs, name)
        except Exception as error:
            logger.info("waiting for queue queue=%s error=%s", name, type(error).__name__)
            time.sleep(2)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    s3_events = boto3.client("sqs", endpoint_url=os.environ["S3_EVENTS_SQS_ENDPOINT_URL"])
    jobs = boto3.client("sqs", endpoint_url=os.environ["JOBS_SQS_ENDPOINT_URL"])
    s3_events_url = _queue_url(s3_events, os.environ.get("S3_EVENTS_QUEUE_NAME", "s3-events"))
    jobs_url = _queue_url(jobs, jobs_queue_name())
    workers = os.environ["WORKER_LAMBDA_URLS"].split(",")  # one RIE container per worker

    threads = [
        threading.Thread(
            target=_forever,
            args=(lambda: relay_once(s3_events, s3_events_url, jobs, jobs_url),),
            daemon=True,
        )
    ]
    for url in workers:
        invoke = rie_invoker(url.strip())
        threads.append(
            threading.Thread(
                target=_forever,
                args=(lambda invoke=invoke: work_once(jobs, jobs_url, invoke, 2),),
                daemon=True,
            )
        )
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


if __name__ == "__main__":
    main()
