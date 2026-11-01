"""Job service wiring that needs only boto3: the API imports this and nothing heavier.

The extraction pipeline (langgraph, Presidio, spaCy, the Gemini SDK) lives in `runtime`. Keeping
it out of this module is what lets the API Lambda start inside API Gateway's 29 s.
"""

import os

import boto3
from botocore.config import Config

from invoice_extraction.adapters.dynamo_jobs import DynamoJobRepository
from invoice_extraction.adapters.s3_blobs import S3BlobStore
from invoice_extraction.application.jobs import JobService
from invoice_extraction.domain.status import UPLOAD_TTL_SECONDS, RetryPolicy

# SigV4 explicitly: botocore may otherwise sign presigned PUTs with legacy SigV2 against the
# global endpoint, which S3 rejects (SignatureDoesNotMatch) for a role's temporary credentials.
_S3_CONFIG = Config(signature_version="s3v4", s3={"addressing_style": "path"})


def s3_client(endpoint_url: str | None = None):
    return boto3.client("s3", endpoint_url=endpoint_url, config=_S3_CONFIG)


def env_number(name: str, default: float, cast: type = int) -> float:
    """The environment variable `name` as `cast`, or `default` when unset."""
    return cast(os.environ.get(name, default))


def build_retry_policy() -> RetryPolicy:
    defaults = RetryPolicy()
    return RetryPolicy(
        max_receives=env_number("MAX_RECEIVES", defaults.max_receives),
        base_seconds=env_number("RETRY_BASE_SECONDS", defaults.base_seconds),
        cap_seconds=env_number("RETRY_CAP_SECONDS", defaults.cap_seconds),
    )


def job_service(extract) -> JobService:
    s3 = s3_client()
    # Optional: only the local stack needs presigned URLs on a host (localhost) other than the
    # one the containers use; on AWS both are the same endpoint.
    public_endpoint = os.environ.get("S3_PUBLIC_ENDPOINT_URL")
    presigner = s3_client(public_endpoint) if public_endpoint else None
    return JobService(
        jobs=DynamoJobRepository(boto3.resource("dynamodb").Table(os.environ["JOBS_TABLE"])),
        blobs=S3BlobStore(s3, os.environ["BUCKET"], presign_client=presigner),
        extract=extract,
        upload_ttl=int(os.environ.get("UPLOAD_TTL_SECONDS", UPLOAD_TTL_SECONDS)),
        retry=build_retry_policy(),
    )


def _api_never_extracts(*args, **kwargs):
    raise RuntimeError("the API does not extract; only the worker does")


def build_api_job_service() -> JobService:
    """The service the API runs: it only creates and reads jobs.

    Skipping the pipeline avoids constructing Presidio and spaCy, which alone takes about as
    long as the API's whole timeout on a cold start.
    """
    return job_service(_api_never_extracts)
