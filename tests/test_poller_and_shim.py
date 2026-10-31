# ruff: noqa: N803
"""Seam 2 (in-process): the poller's S3 event relay and workers, and the API shim."""

import json

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from invoice_extraction.entrypoints.api_shim import create_app
from invoice_extraction.entrypoints.poller import relay_once, work_once
from invoice_extraction.entrypoints.redrive import redrive


@pytest.fixture
def queues(monkeypatch):
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(name, "test")
    with mock_aws():
        sqs = boto3.client("sqs", region_name="us-east-1")
        yield (
            sqs,
            sqs.create_queue(QueueName="s3-events")["QueueUrl"],
            sqs.create_queue(QueueName="jobs", Attributes={"VisibilityTimeout": "0"})["QueueUrl"],
        )


def drain(sqs, url):
    out = []
    while messages := sqs.receive_message(QueueUrl=url, MaxNumberOfMessages=10).get("Messages"):
        out += [m["Body"] for m in messages]
        for message in messages:
            sqs.delete_message(QueueUrl=url, ReceiptHandle=message["ReceiptHandle"])
    return out


def test_relay_skips_the_s3_test_event_and_forwards_real_notifications(queues):
    sqs, source, dest = queues
    sqs.send_message(QueueUrl=source, MessageBody=json.dumps({"Event": "s3:TestEvent"}))
    real = json.dumps({"Records": [{"s3": {"object": {"key": "uploads%2Fa.pdf"}}}]})
    sqs.send_message(QueueUrl=source, MessageBody=real)

    while relay_once(sqs, source, sqs, dest):
        pass

    assert drain(sqs, dest) == [real]
    assert drain(sqs, source) == []


def test_worker_delivers_an_sqs_event_and_deletes_on_success(queues):
    sqs, _, jobs = queues
    sqs.send_message(QueueUrl=jobs, MessageBody="{}")
    seen = []

    def invoke(event):
        seen.append(event)
        return {"batchItemFailures": []}

    assert work_once(sqs, jobs, invoke) is True

    (record,) = seen[0]["Records"]
    assert record["eventSource"] == "aws:sqs"
    assert record["body"] == "{}"
    assert record["attributes"]["ApproximateReceiveCount"] == "1"
    assert drain(sqs, jobs) == []


@pytest.mark.parametrize("outcome", ["failure", "crash"])
def test_worker_leaves_the_message_for_redelivery_on_failure(queues, outcome):
    sqs, _, jobs = queues
    sqs.send_message(QueueUrl=jobs, MessageBody="{}")

    def invoke(event):
        if outcome == "crash":
            raise ConnectionError("rie down")
        return {"batchItemFailures": [{"itemIdentifier": event["Records"][0]["messageId"]}]}

    work_once(sqs, jobs, invoke)

    assert drain(sqs, jobs) == ["{}"]


def test_shim_translates_http_to_api_gateway_proxy_events():
    events = []

    def invoke(event):
        events.append(event)
        return {"statusCode": 201, "headers": {}, "body": '{"job_id": "j1"}'}

    client = TestClient(create_app(invoke))

    created = client.post("/jobs")
    fetched = client.get("/jobs/j1")

    assert created.status_code == 201
    assert created.json() == {"job_id": "j1"}
    assert events[0]["httpMethod"] == "POST" and events[0]["path"] == "/jobs"
    assert events[1]["httpMethod"] == "GET"
    assert events[1]["pathParameters"] == {"job_id": "j1"}
    assert fetched.status_code == 201


def ok_invoke(event):
    return {"statusCode": 200, "headers": {}, "body": "{}"}


def test_shim_passes_headers_through_to_the_lambda():
    events = []

    def invoke(event):
        events.append(event)
        return ok_invoke(event)

    TestClient(create_app(invoke)).post("/jobs", headers={"Idempotency-Key": "k1"})

    assert events[0]["headers"]["idempotency-key"] == "k1"


def test_shim_rejects_a_bad_api_key_with_a_json_403():
    client = TestClient(create_app(ok_invoke, api_key="secret"))

    missing = client.post("/jobs")
    wrong = client.get("/jobs/j1", headers={"x-api-key": "nope"})
    right = client.post("/jobs", headers={"x-api-key": "secret"})

    assert missing.status_code == wrong.status_code == 403
    assert missing.headers["content-type"] == "application/json"
    assert missing.json() == {"message": "Forbidden"}
    assert right.status_code == 200


def test_shim_throttles_with_a_json_429_and_recovers():
    now = [0.0]
    client = TestClient(create_app(ok_invoke, rate_per_second=1, burst=2, clock=lambda: now[0]))

    codes = [client.post("/jobs").status_code for _ in range(3)]
    throttled = client.post("/jobs")
    now[0] += 1.0
    after = client.post("/jobs").status_code

    assert codes == [200, 200, 429]
    assert throttled.headers["content-type"] == "application/json"
    assert throttled.json() == {"message": "Too Many Requests"}
    assert after == 200


def test_shim_enforces_a_daily_post_quota_but_not_on_gets():
    now = [0.0]
    client = TestClient(
        create_app(
            ok_invoke, rate_per_second=100, burst=100, daily_post_limit=3, clock=lambda: now[0]
        )
    )

    codes = [client.post("/jobs").status_code for _ in range(4)]
    get = client.get("/jobs/j1").status_code
    now[0] += 24 * 3600
    next_day = client.post("/jobs").status_code

    assert codes == [200, 200, 200, 429]
    assert get == 200
    assert next_day == 200


class StubSqs:
    """moto cannot move messages, so the native redrive calls are recorded here."""

    def __init__(self):
        self.started = []
        self.polls = 0

    def get_queue_url(self, QueueName):
        return {"QueueUrl": f"http://q/{QueueName}"}

    def get_queue_attributes(self, QueueUrl, AttributeNames):
        return {"Attributes": {"QueueArn": "arn:aws:sqs:us-east-1:0:" + QueueUrl.rsplit("/")[-1]}}

    def start_message_move_task(self, SourceArn, DestinationArn):
        self.started.append((SourceArn, DestinationArn))

    def list_message_move_tasks(self, SourceArn):
        self.polls += 1
        status = "RUNNING" if self.polls < 2 else "COMPLETED"
        return {"Results": [{"Status": status, "ApproximateNumberOfMessagesMoved": 3}]}


def test_redrive_moves_the_dlq_back_to_the_jobs_queue_natively():
    sqs = StubSqs()

    task = redrive(sqs, wait_seconds=5)

    assert sqs.started == [("arn:aws:sqs:us-east-1:0:jobs-dlq", "arn:aws:sqs:us-east-1:0:jobs")]
    assert task["Status"] == "COMPLETED"
