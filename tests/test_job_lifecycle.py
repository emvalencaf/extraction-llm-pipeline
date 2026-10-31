"""Seam 2 (in-process): job state machine, idempotency and queue behavior.

Real handlers and use cases over moto-backed DynamoDB, S3 and SQS; the model is FakeGemini.
"""

import json

import boto3
import pytest
from moto import mock_aws

from invoice_extraction.adapters.dynamo_jobs import DynamoJobRepository
from invoice_extraction.adapters.fake_gemini import FakeGemini
from invoice_extraction.adapters.s3_blobs import S3BlobStore
from invoice_extraction.adapters.sqs_visibility import SqsVisibility
from invoice_extraction.application.jobs import JobService
from invoice_extraction.application.ports import TransientModelError
from invoice_extraction.composition.container import build_extract_invoice
from invoice_extraction.domain.status import (
    IllegalTransitionError,
    JobStatus,
    transition_sources,
)
from invoice_extraction.entrypoints.api_handler import make_api_handler
from invoice_extraction.entrypoints.poller import work_once
from invoice_extraction.entrypoints.worker_handler import make_worker_handler
from support.invoices import invoice_pdf, raw_extraction

BUCKET = "invoices"
TABLE = "jobs"
MAX_RECEIVES = 5


class Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


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


@pytest.fixture
def clock():
    return Clock()


def make_service(model, clock, retry_base=10):
    return JobService(
        jobs=DynamoJobRepository(boto3.resource("dynamodb", region_name="us-east-1").Table(TABLE)),
        blobs=S3BlobStore(boto3.client("s3", region_name="us-east-1"), BUCKET),
        extract=build_extract_invoice(model, sleep=lambda _: None),
        clock=clock,
        max_receives=MAX_RECEIVES,
        retry_base_seconds=retry_base,
        retry_cap_seconds=60,
    )


def upload(job_id, body=None):
    boto3.client("s3", region_name="us-east-1").put_object(
        Bucket=BUCKET, Key=f"uploads/{job_id}.pdf", Body=body or invoice_pdf()
    )


def sqs_event(job_id, receive=1, message_id="m1"):
    key = f"uploads/{job_id}.pdf"
    notification = {"Records": [{"s3": {"object": {"key": key}}}]}
    return {
        "Records": [
            {
                "messageId": message_id,
                "receiptHandle": "rh",
                "body": json.dumps(notification),
                "attributes": {"ApproximateReceiveCount": str(receive)},
            }
        ]
    }


class RecordingDelayer:
    def __init__(self):
        self.calls = []

    def delay(self, receipt_handle, seconds):
        self.calls.append((receipt_handle, seconds))


def api_event(method, path, headers=None):
    return {
        "httpMethod": method,
        "path": path,
        "headers": headers or {},
        "pathParameters": None if path == "/jobs" else {"job_id": path.rsplit("/", 1)[-1]},
    }


def good_model():
    return FakeGemini(reply=raw_extraction())


def unavailable_model():
    model = FakeGemini(reply=raw_extraction())
    for name in ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite"):
        model.inject(name, TransientModelError("429"))
    return model


# --- state machine -------------------------------------------------------------------


def test_transition_table_forbids_leaving_terminal_states():
    for terminal in (JobStatus.SUCCEEDED, JobStatus.FAILED_VALIDATION, JobStatus.EXPIRED):
        for target in JobStatus:
            assert terminal not in transition_sources(target)


def test_conditional_write_rejects_an_illegal_transition(aws, clock):
    svc = make_service(good_model(), clock)
    job = svc.create()
    repo = svc.jobs
    repo.transition(job["job_id"], JobStatus.EXPIRED, expected={JobStatus.AWAITING_UPLOAD})

    with pytest.raises(IllegalTransitionError):
        repo.transition(job["job_id"], JobStatus.PROCESSING, expected={JobStatus.AWAITING_UPLOAD})

    assert svc.get(job["job_id"])["status"] == "expired"


def test_only_one_of_two_concurrent_claims_wins(aws, clock):
    svc = make_service(good_model(), clock)
    job = svc.create()
    upload(job["job_id"])
    sources = {JobStatus.AWAITING_UPLOAD, JobStatus.QUEUED}

    svc.jobs.transition(job["job_id"], JobStatus.PROCESSING, expected=sources)
    with pytest.raises(IllegalTransitionError):
        svc.jobs.transition(job["job_id"], JobStatus.PROCESSING, expected=sources)


def test_a_job_whose_upload_never_arrives_expires(aws, clock):
    svc = make_service(good_model(), clock)
    job = svc.create()
    assert svc.get(job["job_id"])["status"] == "awaiting_upload"

    clock.now += 15 * 60 + 1

    assert svc.get(job["job_id"])["status"] == "expired"


def test_an_upload_arriving_after_expiry_is_ignored(aws, clock):
    svc = make_service(good_model(), clock)
    worker = make_worker_handler(svc)
    job = svc.create()
    clock.now += 15 * 60 + 1
    svc.get(job["job_id"])
    upload(job["job_id"])

    out = worker(sqs_event(job["job_id"]), None)

    assert out == {"batchItemFailures": []}
    assert svc.get(job["job_id"])["status"] == "expired"


# --- duplicate work ------------------------------------------------------------------


def test_a_duplicate_delivery_does_not_run_the_pipeline_twice(aws, clock):
    model = good_model()
    svc = make_service(model, clock)
    worker = make_worker_handler(svc)
    job = svc.create()
    upload(job["job_id"])

    worker(sqs_event(job["job_id"]), None)
    again = worker(sqs_event(job["job_id"], receive=2), None)

    assert again == {"batchItemFailures": []}
    assert len(model.calls) == 1
    assert svc.get(job["job_id"])["status"] == "succeeded"


def test_a_repeated_idempotency_key_returns_the_same_job(aws, clock):
    api = make_api_handler(make_service(good_model(), clock))
    headers = {"Idempotency-Key": "abc"}

    first = api(api_event("POST", "/jobs", headers), None)
    second = api(api_event("POST", "/jobs", {"idempotency-key": "abc"}), None)
    other = api(api_event("POST", "/jobs", {"Idempotency-Key": "xyz"}), None)
    unkeyed = [api(api_event("POST", "/jobs"), None) for _ in range(2)]

    ids = [json.loads(r["body"])["job_id"] for r in (first, second, other, *unkeyed)]
    assert first["statusCode"] == 201 and second["statusCode"] == 200
    assert ids[0] == ids[1]
    assert len(set(ids)) == 4


# --- queue behavior ------------------------------------------------------------------


def test_model_unavailable_requeues_the_job_with_a_growing_visibility_delay(aws, clock):
    svc = make_service(unavailable_model(), clock)
    delayer = RecordingDelayer()
    worker = make_worker_handler(svc, delayer=delayer)
    job = svc.create()
    upload(job["job_id"])

    delays = []
    for receive in (1, 2, 3, 4):
        out = worker(sqs_event(job["job_id"], receive=receive), None)
        assert out == {"batchItemFailures": [{"itemIdentifier": "m1"}]}
        delays.append(delayer.calls[-1][1])

    assert delays == [10, 20, 40, 60]  # doubles per receive, capped
    assert svc.get(job["job_id"])["status"] == "queued"


def test_the_last_receive_marks_the_job_failed(aws, clock):
    svc = make_service(unavailable_model(), clock)
    worker = make_worker_handler(svc, delayer=RecordingDelayer())
    job = svc.create()
    upload(job["job_id"])

    out = worker(sqs_event(job["job_id"], receive=MAX_RECEIVES), None)

    assert out == {"batchItemFailures": [{"itemIdentifier": "m1"}]}
    stored = svc.get(job["job_id"])
    assert stored["status"] == "failed"
    assert stored["errors"] == ["retries_exhausted"]


def test_a_missing_upload_on_the_last_receive_marks_the_job_failed(aws, clock):
    svc = make_service(good_model(), clock)
    job = svc.create()

    make_worker_handler(svc)(sqs_event(job["job_id"], receive=MAX_RECEIVES), None)

    assert svc.get(job["job_id"])["status"] == "failed"


def test_an_oversized_upload_is_rejected_by_the_worker_without_the_pipeline(aws, clock):
    model = good_model()
    svc = make_service(model, clock)
    job = svc.create()
    upload(job["job_id"], body=b"0" * (5 * 1024 * 1024 + 1))

    out = make_worker_handler(svc)(sqs_event(job["job_id"]), None)

    assert out == {"batchItemFailures": []}
    stored = svc.get(job["job_id"])
    assert stored["status"] == "failed"
    assert stored["reason"] == "pdf_too_large"
    assert model.calls == []


def test_a_poison_message_ends_in_the_dlq_with_the_job_failed(aws, clock):
    sqs = boto3.client("sqs", region_name="us-east-1")
    dlq_url = sqs.create_queue(QueueName="jobs-dlq")["QueueUrl"]
    dlq_arn = sqs.get_queue_attributes(QueueUrl=dlq_url, AttributeNames=["QueueArn"])["Attributes"][
        "QueueArn"
    ]
    jobs_url = sqs.create_queue(
        QueueName="jobs",
        Attributes={
            "VisibilityTimeout": "0",
            "RedrivePolicy": json.dumps(
                {"deadLetterTargetArn": dlq_arn, "maxReceiveCount": MAX_RECEIVES}
            ),
        },
    )["QueueUrl"]
    svc = make_service(unavailable_model(), clock, retry_base=0)
    worker = make_worker_handler(svc, delayer=SqsVisibility(sqs, jobs_url))
    job = svc.create()
    upload(job["job_id"])
    notification = {"Records": [{"s3": {"object": {"key": f"uploads/{job['job_id']}.pdf"}}}]}
    sqs.send_message(QueueUrl=jobs_url, MessageBody=json.dumps(notification))

    for _ in range(MAX_RECEIVES + 2):
        work_once(sqs, jobs_url, lambda event: worker(event, None))

    in_dlq = sqs.receive_message(QueueUrl=dlq_url, MaxNumberOfMessages=10).get("Messages", [])
    assert len(in_dlq) == 1
    assert svc.get(job["job_id"])["status"] == "failed"


def test_redrive_replays_a_failed_job(aws, clock):
    model = FakeGemini(reply=raw_extraction())
    for name in ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite"):
        model.inject(name, TransientModelError("429"), times=3)
    svc = make_service(model, clock)
    worker = make_worker_handler(svc, delayer=RecordingDelayer())
    job = svc.create()
    upload(job["job_id"])
    worker(sqs_event(job["job_id"], receive=MAX_RECEIVES), None)
    assert svc.get(job["job_id"])["status"] == "failed"

    # the outage is over; the DLQ message is moved back and delivered afresh
    out = worker(sqs_event(job["job_id"], receive=1), None)

    assert out == {"batchItemFailures": []}
    assert svc.get(job["job_id"])["status"] == "succeeded"


def test_a_business_failure_is_final_even_if_redelivered(aws, clock):
    reply = raw_extraction()
    reply["totals"]["gross_amount"] = "n/a"
    model = FakeGemini(reply=reply)
    svc = make_service(model, clock)
    worker = make_worker_handler(svc)
    job = svc.create()
    upload(job["job_id"])
    worker(sqs_event(job["job_id"]), None)
    calls = len(model.calls)

    worker(sqs_event(job["job_id"], receive=2), None)

    assert len(model.calls) == calls
    assert svc.get(job["job_id"])["status"] == "failed_validation"
