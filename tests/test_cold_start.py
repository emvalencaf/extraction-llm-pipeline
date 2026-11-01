"""Lambda cold start: the API never builds the extraction pipeline, and handlers wire once."""

import pytest

from invoice_extraction.composition import runtime, service
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

    assert service.build_api_job_service() is not None


def test_the_api_handler_wires_its_service_once_across_invocations(monkeypatch):
    built = []
    monkeypatch.setattr(service, "build_api_job_service", lambda: built.append(1) or object())
    monkeypatch.setattr(api_handler, "make_api_handler", lambda svc: lambda e, c: {"ok": 1})
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


def test_the_s3_client_signs_presigned_urls_with_sigv4(aws_env, monkeypatch):
    """Legacy SigV2 URLs are rejected by S3 when signed with a Lambda role's temporary keys."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIDEXAMPLE")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "token")

    url = service.s3_client().generate_presigned_url(
        "put_object", Params={"Bucket": "bucket", "Key": "uploads/a.pdf"}, ExpiresIn=900
    )

    assert "X-Amz-Signature=" in url
    assert "AWSAccessKeyId=" not in url


def test_importing_the_api_path_loads_none_of_the_heavy_dependencies():
    """The API's cold start is dominated by imports: it must not pay for the pipeline."""
    import subprocess
    import sys

    code = (
        "import sys\n"
        "import invoice_extraction.entrypoints.api_handler as h\n"
        "import invoice_extraction.composition.service\n"
        "heavy = {'langgraph', 'presidio_analyzer', 'spacy', 'google.genai'}\n"
        "loaded = sorted(m for m in heavy if m in sys.modules)\n"
        "assert not loaded, loaded\n"
    )
    result = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
