"""Seam 2 (in-process): the boto3 init and the HTTP fake-gemini."""

import time

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


def _extract(client, model):
    return client.post("/extract", json={"model": model, "text": "t", "schema": {}})


def test_a_scenario_fails_only_the_targeted_model_for_a_number_of_calls():
    client = TestClient(create_app())
    client.post(
        "/control/scenario",
        json={"mode": "error", "status": 429, "model": "primary", "times": 2},
    )

    codes = [
        _extract(client, "primary").status_code,
        _extract(client, "fallback").status_code,
        _extract(client, "primary").status_code,
        _extract(client, "primary").status_code,
    ]

    assert codes == [429, 200, 429, 200]


def test_a_scenario_without_a_model_or_times_hits_every_call_until_cleared():
    client = TestClient(create_app())
    client.post("/control/scenario", json={"mode": "error", "status": 503})

    failing = [_extract(client, m).status_code for m in ("a", "b", "a")]
    client.delete("/control/scenario")
    recovered = _extract(client, "a").status_code

    assert failing == [503, 503, 503]
    assert recovered == 200


def test_a_scenario_can_replace_or_patch_the_reply():
    client = TestClient(create_app())
    client.post("/control/scenario", json={"mode": "reply", "reply": {"invoice_no": "X"}})
    replaced = _extract(client, "m").json()
    client.delete("/control/scenario")
    client.post(
        "/control/scenario",
        json={"mode": "reply", "patch": {"totals": {"gross_amount": "1.00"}}, "times": 1},
    )
    patched = _extract(client, "m").json()

    assert replaced == {"invoice_no": "X"}
    assert patched["totals"]["gross_amount"] == "1.00"
    assert patched["totals"]["net_amount"] == "667,080.00"  # the rest of the default stays
    assert patched["invoice_no"] == "51109301"


def test_crash_mode_hangs_the_call_so_a_caller_times_out():
    client = TestClient(create_app())
    client.post("/control/scenario", json={"mode": "crash", "hang_seconds": 0.2})

    started = time.monotonic()
    response = _extract(client, "m")

    assert time.monotonic() - started >= 0.2
    assert response.status_code == 504


def test_the_call_log_records_each_model_call_and_is_cleared_with_the_scenarios():
    client = TestClient(create_app())
    client.post("/control/scenario", json={"mode": "error", "status": 503, "model": "a"})
    _extract(client, "a")
    _extract(client, "b")

    assert client.get("/control/calls").json() == [
        {"model": "a", "outcome": "error:503"},
        {"model": "b", "outcome": "ok"},
    ]
    client.delete("/control/scenario")
    assert client.get("/control/calls").json() == []
