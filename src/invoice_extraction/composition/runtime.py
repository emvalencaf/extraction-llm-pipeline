"""Wire the job service from environment variables (the only configuration channel).

Variables: JOBS_TABLE, BUCKET, GEMINI_API_KEY (real Gemini adapter; wins when set) or
FAKE_GEMINI_URL (HTTP model service otherwise), optional S3_PUBLIC_ENDPOINT_URL (host
named in presigned URLs). boto3 itself honors AWS_ENDPOINT_URL_<SERVICE>, AWS_REGION and the credentials variables.
"""

import os

import boto3
from botocore.config import Config
from google import genai

from invoice_extraction.adapters.dynamo_jobs import DynamoJobRepository
from invoice_extraction.adapters.gemini import GeminiExtractionModel
from invoice_extraction.adapters.http_model import HttpExtractionModel
from invoice_extraction.adapters.json_events import JsonEventSink
from invoice_extraction.adapters.s3_blobs import S3BlobStore
from invoice_extraction.application.jobs import JobService
from invoice_extraction.application.ports import ExtractionModel
from invoice_extraction.composition.container import build_extract_invoice

_PATH_STYLE = Config(s3={"addressing_style": "path"})


def build_model() -> ExtractionModel:
    """The real Gemini adapter when GEMINI_API_KEY is set, else the fake over HTTP."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        return GeminiExtractionModel(genai.Client(api_key=api_key))
    return HttpExtractionModel(os.environ["FAKE_GEMINI_URL"])


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
        extract=build_extract_invoice(build_model(), sink=JsonEventSink()),
    )
