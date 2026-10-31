"""Wire the job service from environment variables (the only configuration channel).

Variables: JOBS_TABLE, BUCKET, GEMINI_API_KEY (real Gemini adapter; wins when set) or
FAKE_GEMINI_URL (HTTP model service otherwise), optional S3_PUBLIC_ENDPOINT_URL (host
named in presigned URLs). Queue behavior: MAX_RECEIVES (5), RETRY_BASE_SECONDS (30),
RETRY_CAP_SECONDS (900), UPLOAD_TTL_SECONDS (900), the in-process retries of a model call
LLM_MAX_ATTEMPTS (3), LLM_BACKOFF_BASE_SECONDS (1), LLM_BACKOFF_CAP_SECONDS (8), and for
the worker JOBS_QUEUE_URL or JOBS_QUEUE_NAME (jobs) to find the queue it delays messages on.
boto3 itself honors AWS_ENDPOINT_URL_<SERVICE>, AWS_REGION and the credentials variables.
"""

import os

import boto3
from botocore.config import Config

from invoice_extraction.adapters.dynamo_jobs import DynamoJobRepository
from invoice_extraction.adapters.gemini import GeminiExtractionModel
from invoice_extraction.adapters.http_model import HttpExtractionModel
from invoice_extraction.adapters.json_events import JsonEventSink
from invoice_extraction.adapters.s3_blobs import S3BlobStore
from invoice_extraction.adapters.sqs_visibility import SqsVisibility
from invoice_extraction.application.jobs import JobService
from invoice_extraction.application.pipeline import RetryPolicy as LlmRetryPolicy
from invoice_extraction.application.ports import ExtractionModel
from invoice_extraction.composition.container import build_extract_invoice
from invoice_extraction.composition.queues import jobs_queue_url
from invoice_extraction.domain.status import UPLOAD_TTL_SECONDS, RetryPolicy

_PATH_STYLE = Config(s3={"addressing_style": "path"})


def build_model() -> ExtractionModel:
    """The real Gemini adapter when GEMINI_API_KEY is set, else the fake over HTTP."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        from google import genai  # lazy: only the real-model path needs the SDK

        return GeminiExtractionModel(genai.Client(api_key=api_key))
    return HttpExtractionModel(os.environ["FAKE_GEMINI_URL"])


def build_retry_policy() -> RetryPolicy:
    defaults = RetryPolicy()
    return RetryPolicy(
        max_receives=int(os.environ.get("MAX_RECEIVES", defaults.max_receives)),
        base_seconds=int(os.environ.get("RETRY_BASE_SECONDS", defaults.base_seconds)),
        cap_seconds=int(os.environ.get("RETRY_CAP_SECONDS", defaults.cap_seconds)),
    )


def build_llm_retry_policy() -> LlmRetryPolicy:
    """Short in-process retries of a model call; compressed in compose, as in production."""
    defaults = LlmRetryPolicy()
    return LlmRetryPolicy(
        max_attempts=int(os.environ.get("LLM_MAX_ATTEMPTS", defaults.max_attempts)),
        base_delay=float(os.environ.get("LLM_BACKOFF_BASE_SECONDS", defaults.base_delay)),
        max_delay=float(os.environ.get("LLM_BACKOFF_CAP_SECONDS", defaults.max_delay)),
    )


def build_job_service() -> JobService:
    s3 = boto3.client("s3", config=_PATH_STYLE)
    # Optional: only the local stack needs presigned URLs on a host (localhost) other than the
    # one the containers use; on AWS both are the same endpoint.
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
            build_model(), sink=JsonEventSink(), retry=build_llm_retry_policy()
        ),
        upload_ttl=int(os.environ.get("UPLOAD_TTL_SECONDS", UPLOAD_TTL_SECONDS)),
        retry=build_retry_policy(),
    )


def build_queue_delayer() -> SqsVisibility:
    sqs = boto3.client("sqs")
    return SqsVisibility(sqs, jobs_queue_url(sqs))
