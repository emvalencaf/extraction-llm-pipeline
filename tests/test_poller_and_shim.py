"""Seam 2 (in-process): the poller's S3 event relay and workers, and the API shim."""

import json

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from invoice_extraction.entrypoints.api_shim import create_app
from invoice_extraction.entrypoints.poller import relay_once, work_once


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
