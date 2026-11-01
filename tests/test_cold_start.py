"""Lambda cold start: the API never builds the extraction pipeline, and handlers wire once."""

import pytest

from invoice_extraction.composition import runtime
from invoice_extraction.entrypoints import api_handler, worker_handler


@pytest.fixture
def aws_env(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("JOBS_TABLE", "jobs")
    monkeypatch.setenv("BUCKET", "bucket")
    monkeypatch.setenv("FAKE_GEMINI_URL", "http://unused.invalid")


def test_the_api_service_does_not_build_the_extraction_pipeline(aws_env, monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("the API must not build the Presidio/spaCy pipeline")

    monkeypatch.setattr(runtime, "build_extract_invoice", boom)
    monkeypatch.setattr(runtime, "build_model", boom)

    assert runtime.build_api_job_service() is not None


def test_the_api_handler_wires_its_service_once_across_invocations(monkeypatch):
    built = []
    monkeypatch.setattr(
        runtime, "build_api_job_service", lambda: built.append(1) or object(), raising=False
    )
    monkeypatch.setattr(api_handler, "make_api_handler", lambda service: lambda e, c: {"ok": 1})
    api_handler._handler.cache_clear()

    api_handler.handler({}, None)
    api_handler.handler({}, None)

    assert len(built) == 1


def test_the_worker_handler_wires_its_service_once_across_invocations(monkeypatch):
    built = []
    monkeypatch.setattr(runtime, "build_job_service", lambda: built.append(1) or object())
    monkeypatch.setattr(runtime, "build_queue_delayer", lambda: object())
    monkeypatch.setattr(
        worker_handler, "make_worker_handler", lambda service, delayer: lambda e, c: {}
    )
    worker_handler._handler.cache_clear()

    worker_handler.handler({}, None)
    worker_handler.handler({}, None)

    assert len(built) == 1
