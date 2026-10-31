"""Seam 2 (in-process): the boto3 init and the HTTP fake-gemini."""

import boto3
from fastapi.testclient import TestClient
from moto import mock_aws

from invoice_extraction.entrypoints.fake_gemini_server import create_app
from invoice_extraction.entrypoints.init_resources import (
    RESOURCES,
    check_against_terraform,
    init,
)


def test_fake_gemini_server_serves_replies_and_a_control_endpoint():
    client = TestClient(create_app())
    call = {"text": "t", "schema": {}}

    default = client.post("/extract", json=call).json()
    client.put("/control/reply", json={"invoice_no": "X"})
    steered = client.post("/extract", json=call).json()
    client.delete("/control/reply")
    restored = client.post("/extract", json=call).json()

    assert default["invoice_no"] == "51109301"
    assert steered == {"invoice_no": "X"}
    assert restored == default


def test_init_is_idempotent_and_routes_uploads_to_the_events_queue(monkeypatch):
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(name, "test")
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        dynamodb = boto3.client("dynamodb", region_name="us-east-1")
        sqs = boto3.client("sqs", region_name="us-east-1")
        init(s3, dynamodb, sqs, sqs)
        init(s3, dynamodb, sqs, sqs)

        s3.put_object(Bucket=RESOURCES["bucket"], Key="uploads/j1.pdf", Body=b"x")
        s3.put_object(Bucket=RESOURCES["bucket"], Key="other/ignored.pdf", Body=b"x")
        url = sqs.get_queue_url(QueueName=RESOURCES["s3_events_queue"])["QueueUrl"]
        bodies = [
            m["Body"] for m in sqs.receive_message(QueueUrl=url, MaxNumberOfMessages=10)["Messages"]
        ]

        assert RESOURCES["table"] in dynamodb.list_tables()["TableNames"]
        assert any("uploads%2Fj1.pdf" in body for body in bodies)
        assert not any("ignored" in body for body in bodies)


def test_terraform_check_is_skipped_until_terraform_exists(tmp_path):
    assert "skipped" in check_against_terraform(tmp_path / "missing")


def test_fake_gemini_server_can_be_told_to_fail():
    client = TestClient(create_app())
    call = {"text": "t", "schema": {}}

    client.put("/control/fail", json={"status": 503})
    failing = client.post("/extract", json=call).status_code
    client.delete("/control/fail")
    recovered = client.post("/extract", json=call).status_code

    assert (failing, recovered) == (503, 200)
