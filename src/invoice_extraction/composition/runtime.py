"""Wire the job service from environment variables (the only configuration channel).

Variables: JOBS_TABLE, BUCKET, GEMINI_API_KEY (real Gemini adapter; wins when set) or
GEMINI_API_KEY_SSM_PARAMETER (name of the SecureString holding it) or FAKE_GEMINI_URL
(HTTP model service otherwise), optional S3_PUBLIC_ENDPOINT_URL (host named in presigned
URLs). Queue behavior: MAX_RECEIVES (5), RETRY_BASE_SECONDS (30),
RETRY_CAP_SECONDS (900), UPLOAD_TTL_SECONDS (900), the in-process retries of a model call
LLM_MAX_ATTEMPTS (3), LLM_BACKOFF_BASE_SECONDS (1), LLM_BACKOFF_CAP_SECONDS (8), and for
the worker JOBS_QUEUE_URL or JOBS_QUEUE_NAME (jobs) to find the queue it delays messages on.
boto3 itself honors AWS_ENDPOINT_URL_<SERVICE>, AWS_REGION and the credentials variables.
"""

import os

import boto3

from invoice_extraction.adapters.gemini import GeminiExtractionModel
from invoice_extraction.adapters.http_model import HttpExtractionModel
from invoice_extraction.adapters.json_events import JsonEventSink
from invoice_extraction.adapters.sqs_visibility import SqsVisibility
from invoice_extraction.application.jobs import JobService
from invoice_extraction.application.pipeline import RetryPolicy as LlmRetryPolicy
from invoice_extraction.application.ports import ExtractionModel
from invoice_extraction.composition.container import build_extract_invoice
from invoice_extraction.composition.queues import jobs_queue_url
from invoice_extraction.composition.service import (
    env_number,
    job_service,
    s3_client,  # noqa: F401  (re-exported)
)


def resolve_gemini_key(ssm=None) -> str | None:
    """GEMINI_API_KEY, else the SecureString named by GEMINI_API_KEY_SSM_PARAMETER, else None.

    On AWS the key never sits in the function's environment: Terraform passes only the
    parameter name and the role may read that one parameter. `ssm` is injectable for tests.
    """
    plain = os.environ.get("GEMINI_API_KEY")
    if plain:
        return plain
    parameter = os.environ.get("GEMINI_API_KEY_SSM_PARAMETER")
    if not parameter:
        return None
    client = ssm or boto3.client("ssm")
    return client.get_parameter(Name=parameter, WithDecryption=True)["Parameter"]["Value"]


def build_model() -> ExtractionModel:
    """The real Gemini adapter when a Gemini key resolves, else the fake over HTTP."""
    api_key = resolve_gemini_key()
    if api_key:
        from google import genai  # lazy: only the real-model path needs the SDK

        return GeminiExtractionModel(genai.Client(api_key=api_key))
    return HttpExtractionModel(os.environ["FAKE_GEMINI_URL"])


def build_llm_retry_policy() -> LlmRetryPolicy:
    """Short in-process retries of a model call; compressed in compose, as in production."""
    defaults = LlmRetryPolicy()
    return LlmRetryPolicy(
        max_attempts=env_number("LLM_MAX_ATTEMPTS", defaults.max_attempts),
        base_delay=env_number("LLM_BACKOFF_BASE_SECONDS", defaults.base_delay, float),
        max_delay=env_number("LLM_BACKOFF_CAP_SECONDS", defaults.max_delay, float),
    )


def build_job_service() -> JobService:
    """The service the worker runs: it extracts, so it builds the model and the pipeline."""
    return job_service(
        build_extract_invoice(build_model(), sink=JsonEventSink(), retry=build_llm_retry_policy())
    )


def build_queue_delayer() -> SqsVisibility:
    sqs = boto3.client("sqs")
    return SqsVisibility(sqs, jobs_queue_url(sqs))
