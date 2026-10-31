"""Seam 2 (in-process): Lambda handlers against moto-backed S3 and DynamoDB."""

import json

import boto3
import pytest
from moto import mock_aws

from invoice_extraction.adapters.dynamo_jobs import DynamoJobRepository
from invoice_extraction.adapters.fake_gemini import FakeGemini
from invoice_extraction.adapters.s3_blobs import S3BlobStore
from invoice_extraction.application.jobs import JobService
from invoice_extraction.composition.container import build_extract_invoice
from invoice_extraction.entrypoints.api_handler import make_api_handler
from invoice_extraction.entrypoints.worker_handler import make_worker_handler
from support.invoices import invoice_pdf, raw_extraction

BUCKET = "invoices"
TABLE = "jobs"


@pytest.fixture
def aws(monkeypatch):
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(name, "test")
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        boto3.client("dynamodb", region_name="us-east-1").create_table(
            TableName=TABLE,
            KeySchema=[{"AttributeName": "job_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "job_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield


def service(model):
    s3 = boto3.client("s3", region_name="us-east-1")
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(TABLE)
    return JobService(
        jobs=DynamoJobRepository(table),
        blobs=S3BlobStore(s3, BUCKET),
        extract=build_extract_invoice(model),
    )


def upload(job_id, body=None):
    boto3.client("s3", region_name="us-east-1").put_object(
        Bucket=BUCKET, Key=f"uploads/{job_id}.pdf", Body=body or invoice_pdf()
    )


def api_event(method, path):
    return {
        "httpMethod": method,
        "path": path,
        "pathParameters": None if path == "/jobs" else {"job_id": path.rsplit("/", 1)[-1]},
    }


def s3_event(key):
    """SQS event whose body is the S3 notification."""
    notification = {"Records": [{"s3": {"bucket": {"name": BUCKET}, "object": {"key": key}}}]}
    return {"Records": [{"messageId": "m1", "body": json.dumps(notification)}]}


def test_create_upload_and_fetch_result_end_to_end(aws):
    svc = service(FakeGemini(reply=raw_extraction()))
    api, worker = make_api_handler(svc), make_worker_handler(svc)

    created = api(api_event("POST", "/jobs"), None)
    assert created["statusCode"] == 201
    job = json.loads(created["body"])
    assert job["status"] == "awaiting_upload"
    assert job["upload_url"].startswith("http")

    upload(job["job_id"])
    assert worker(s3_event(f"uploads/{job['job_id']}.pdf"), None) == {"batchItemFailures": []}

    fetched = api(api_event("GET", f"/jobs/{job['job_id']}"), None)
    body = json.loads(fetched["body"])
    assert body["status"] == "succeeded"
    assert body["result"]["issue_date"] == "2023-07-03"
    assert body["result"]["totals"]["gross_amount"] == "733788.00"


def test_unknown_job_is_404(aws):
    api = make_api_handler(service(FakeGemini(reply=raw_extraction())))

    assert api(api_event("GET", "/jobs/nope"), None)["statusCode"] == 404


def test_worker_decodes_url_encoded_keys(aws):
    svc = service(FakeGemini(reply=raw_extraction()))
    job = svc.create()
    upload(job["job_id"])

    make_worker_handler(svc)(s3_event(f"uploads%2F{job['job_id']}.pdf"), None)

    assert svc.get(job["job_id"])["status"] == "succeeded"


def test_worker_records_validation_failure(aws):
    reply = raw_extraction()
    reply["totals"]["gross_amount"] = "n/a"
    svc = service(FakeGemini(reply=reply))
    job = svc.create()
    upload(job["job_id"])

    make_worker_handler(svc)(s3_event(f"uploads/{job['job_id']}.pdf"), None)

    stored = svc.get(job["job_id"])
    assert stored["status"] == "failed_validation"
    assert any("totals.gross_amount" in e for e in stored["errors"])


def test_worker_reports_failure_when_the_pdf_is_missing(aws):
    svc = service(FakeGemini(reply=raw_extraction()))
    job = svc.create()

    out = make_worker_handler(svc)(s3_event(f"uploads/{job['job_id']}.pdf"), None)

    assert out == {"batchItemFailures": [{"itemIdentifier": "m1"}]}
