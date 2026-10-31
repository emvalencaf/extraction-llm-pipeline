"""Wire the job service from environment variables (the only configuration channel).

Variables: JOBS_TABLE, BUCKET, FAKE_GEMINI_URL (model service), optional
S3_PUBLIC_ENDPOINT_URL (host named in presigned URLs). Queue behavior: MAX_RECEIVES (5),
RETRY_BASE_SECONDS (30), RETRY_CAP_SECONDS (900), UPLOAD_TTL_SECONDS (900), and for the
worker JOBS_QUEUE_URL or JOBS_QUEUE_NAME (jobs) to find the queue it delays messages on.
boto3 itself honors AWS_ENDPOINT_URL_<SERVICE>, AWS_REGION and the credentials variables.
"""

import os

import boto3
from botocore.config import Config

from invoice_extraction.adapters.dynamo_jobs import DynamoJobRepository
from invoice_extraction.adapters.http_model import HttpExtractionModel
from invoice_extraction.adapters.json_events import JsonEventSink
from invoice_extraction.adapters.s3_blobs import S3BlobStore
from invoice_extraction.adapters.sqs_visibility import SqsVisibility
from invoice_extraction.application.jobs import JobService
from invoice_extraction.composition.container import build_extract_invoice
from invoice_extraction.domain.status import UPLOAD_TTL_SECONDS

_PATH_STYLE = Config(s3={"addressing_style": "path"})


def build_job_service() -> JobService:
    s3 = boto3.client("s3", config=_PATH_STYLE)
    public_endpoint = os.environ.get("S3_PUBLIC_ENDPOINT_URL")
    presigner = (
        boto3.client("s3", endpoint_url=public_endpoint, config=_PATH_STYLE)
        if public_endpoint
        else None
    )
    return JobService(
        jobs=DynamoJobRepository(boto3.resource("dynamodb").Table(os.environ["JOBS_TABLE"])),
        blobs=S3BlobStore(s3, os.environ["BUCKET"], presign_client=presigner),
        extract=build_extract_invoice(
            HttpExtractionModel(os.environ["FAKE_GEMINI_URL"]), sink=JsonEventSink()
        ),
        upload_ttl=int(os.environ.get("UPLOAD_TTL_SECONDS", UPLOAD_TTL_SECONDS)),
        max_receives=int(os.environ.get("MAX_RECEIVES", 5)),
        retry_base_seconds=int(os.environ.get("RETRY_BASE_SECONDS", 30)),
        retry_cap_seconds=int(os.environ.get("RETRY_CAP_SECONDS", 900)),
    )


def build_queue_delayer() -> SqsVisibility:
    sqs = boto3.client("sqs")
    url = (
        os.environ.get("JOBS_QUEUE_URL")
        or sqs.get_queue_url(QueueName=os.environ.get("JOBS_QUEUE_NAME", "jobs"))["QueueUrl"]
    )
    return SqsVisibility(sqs, url)
