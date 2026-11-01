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


def _env_number(name: str, default: float, cast: type = int) -> float:
    """The environment variable `name` as `cast`, or `default` when unset."""
    return cast(os.environ.get(name, default))


def build_retry_policy() -> RetryPolicy:
    defaults = RetryPolicy()
    return RetryPolicy(
        max_receives=_env_number("MAX_RECEIVES", defaults.max_receives),
        base_seconds=_env_number("RETRY_BASE_SECONDS", defaults.base_seconds),
        cap_seconds=_env_number("RETRY_CAP_SECONDS", defaults.cap_seconds),
    )


def build_llm_retry_policy() -> LlmRetryPolicy:
    """Short in-process retries of a model call; compressed in compose, as in production."""
    defaults = LlmRetryPolicy()
    return LlmRetryPolicy(
        max_attempts=_env_number("LLM_MAX_ATTEMPTS", defaults.max_attempts),
        base_delay=_env_number("LLM_BACKOFF_BASE_SECONDS", defaults.base_delay, float),
        max_delay=_env_number("LLM_BACKOFF_CAP_SECONDS", defaults.max_delay, float),
    )


def _job_service(extract) -> JobService:
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
        extract=extract,
        upload_ttl=int(os.environ.get("UPLOAD_TTL_SECONDS", UPLOAD_TTL_SECONDS)),
        retry=build_retry_policy(),
    )


def build_job_service() -> JobService:
    """The service the worker runs: it extracts, so it builds the model and the pipeline."""
    return _job_service(
        build_extract_invoice(build_model(), sink=JsonEventSink(), retry=build_llm_retry_policy())
    )


def _api_never_extracts(*args, **kwargs):
    raise RuntimeError("the API does not extract; only the worker does")


def build_api_job_service() -> JobService:
    """The service the API runs: it only creates and reads jobs.

    Skipping the pipeline avoids constructing Presidio and spaCy, which alone takes about as
    long as the API's whole timeout on a cold start.
    """
    return _job_service(_api_never_extracts)


def build_queue_delayer() -> SqsVisibility:
    sqs = boto3.client("sqs")
    return SqsVisibility(sqs, jobs_queue_url(sqs))
