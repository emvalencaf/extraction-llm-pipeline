"""Seam 1: wide events (`llm_call`, `job`) and EMF metrics, through the pipeline use case."""

import io
import json

import pytest

from invoice_extraction.adapters.bundle_loader import load_bundle
from invoice_extraction.adapters.fake_gemini import FakeGemini
from invoice_extraction.adapters.json_events import JsonEventSink, to_record
from invoice_extraction.application.observability import JobEvent
from invoice_extraction.application.ports import ModelUnavailableError, TransientModelError
from invoice_extraction.composition.container import build_extract_invoice
from invoice_extraction.domain.status import JobStatus
from support.events import RecordingSink
from support.invoices import (
    SENSITIVE_VALUES,
    TWO_COLUMN_TEXT,
    invoice_pdf,
    raw_extraction,
)
from support.pdf import make_pdf

BUNDLE = load_bundle()
PRIMARY, FALLBACK = BUNDLE.primary.name, BUNDLE.fallback.name


def run(model, sink, pdf=None, **options):
    extract = build_extract_invoice(
        model, sink=sink, sleep=lambda _: None, rng=lambda: 0.5, **options
    )
    return extract(pdf or invoice_pdf(), job_id="job-1")


# --- one llm_call per Gemini call, one job per job -------------------------------------


def test_one_llm_call_event_per_gemini_call_and_one_job_event():
    sink = RecordingSink()
    model = FakeGemini(reply=raw_extraction(), input_tokens=120, output_tokens=45)

    result = run(model, sink)

    assert result.status is JobStatus.SUCCEEDED
    (call,) = sink.llm_calls
    assert (call.model, call.tier, call.outcome) == (PRIMARY, "primary", "ok")
    assert (call.input_tokens, call.output_tokens) == (120, 45)
    assert call.prompt_version == BUNDLE.version
    assert call.latency_ms >= 0
    (job,) = sink.jobs
    assert job.job_id == "job-1"
    assert job.outcome == "succeeded"
    assert job.llm_calls == 1
    assert (job.input_tokens, job.output_tokens) == (120, 45)
    assert job.model == PRIMARY
    assert job.prompt_version == BUNDLE.version


def test_retries_fallback_and_repairs_each_get_their_own_llm_call_event():
    sink = RecordingSink()
    model = FakeGemini(reply=raw_extraction())
    model.inject(PRIMARY, TransientModelError("429"))

    run(model, sink)

    outcomes = [(e.model, e.tier, e.outcome) for e in sink.llm_calls]
    assert outcomes == [(PRIMARY, "primary", "transient_error")] * 3 + [
        (FALLBACK, "fallback", "ok")
    ]
    (job,) = sink.jobs
    assert job.llm_calls == 4
    assert job.fell_back is True
    assert job.model == FALLBACK


def test_repair_attempts_are_flagged_on_the_event():
    sink = RecordingSink()
    bad = raw_extraction()
    bad["totals"]["gross_amount"] = "n/a"
    replies = iter([bad, raw_extraction()])
    model = FakeGemini(reply=lambda _: next(replies))

    run(model, sink)

    assert [e.repair for e in sink.llm_calls] == [False, True]
    (job,) = sink.jobs
    assert job.repairs == 1


def test_job_event_for_a_business_failure_and_for_an_outage():
    sink = RecordingSink()
    run(FakeGemini(reply=raw_extraction()), sink, pdf=b"not a pdf")
    assert sink.llm_calls == []
    (job,) = sink.jobs
    assert (job.outcome, job.reason) == ("failed", "pdf_unreadable")

    sink = RecordingSink()
    model = FakeGemini(reply=raw_extraction())
    model.inject(PRIMARY, TransientModelError("429"))
    model.inject(FALLBACK, TransientModelError("429"))
    with pytest.raises(ModelUnavailableError):
        run(model, sink)
    (job,) = sink.jobs
    assert job.outcome == "unavailable"


def test_job_event_carries_the_grounding_rate():
    sink = RecordingSink()

    run(FakeGemini(reply=raw_extraction()), sink)

    (job,) = sink.jobs
    assert job.grounding_rate == 12 / 14
    assert job.ungrounded_fields == ("currency", "totals.vat_amount")


# --- JSON lines, EMF and privacy -------------------------------------------------------


def logged_lines(model=None, pdf=None) -> list[dict]:
    stream = io.StringIO()
    run(
        model or FakeGemini(reply=raw_extraction(), input_tokens=10, output_tokens=5),
        JsonEventSink(stream),
        pdf=pdf,
    )
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def test_events_are_one_json_object_per_line():
    llm_call, job = logged_lines()

    assert llm_call["event"] == "llm_call"
    assert llm_call["model"] == PRIMARY
    assert llm_call["input_tokens"] == 10
    assert job["event"] == "job"
    assert job["outcome"] == "succeeded"
    assert job["grounding_rate"] == pytest.approx(12 / 14)


def test_metrics_are_emf_without_dimensions():
    for line in logged_lines():
        (directive,) = line["_aws"]["CloudWatchMetrics"]
        assert directive["Dimensions"] == [[]]
        assert directive["Namespace"]
        assert directive["Metrics"]
        for metric in directive["Metrics"]:
            assert isinstance(line[metric["Name"]], int | float)


def test_job_metrics_cover_outcome_duration_and_grounding():
    _, job = logged_lines()

    names = {m["Name"] for m in job["_aws"]["CloudWatchMetrics"][0]["Metrics"]}
    assert {"JobSucceeded", "JobFailed", "JobDurationMs", "GroundingRate"} <= names
    assert (job["JobSucceeded"], job["JobFailed"]) == (1, 0)


@pytest.mark.parametrize(
    ("outcome", "infra_failed"),
    [
        ("succeeded", 0),
        ("failed_validation", 0),  # a bad document is a business failure, not an outage
        ("failed", 1),
        ("unavailable", 1),
        ("error", 1),
    ],
)
def test_job_infra_failed_metric_separates_outages_from_business_failures(outcome, infra_failed):
    record = to_record(JobEvent(outcome=outcome, duration_ms=1.0, prompt_version="v"))

    names = {m["Name"] for m in record["_aws"]["CloudWatchMetrics"][0]["Metrics"]}
    assert "JobInfraFailed" in names
    assert record["JobInfraFailed"] == infra_failed
    assert record["JobFailed"] == (0 if outcome == "succeeded" else 1)


def test_no_invoice_content_appears_in_any_log_line():
    leaky = FakeGemini(reply=raw_extraction())
    leaky.inject(PRIMARY, TransientModelError("429 for invoice 51109301 of Raj Electronics"))
    runs = [
        logged_lines(),
        logged_lines(leaky),
        logged_lines(pdf=make_pdf(TWO_COLUMN_TEXT.splitlines())),
        logged_lines(pdf=b"not a pdf"),
    ]
    reply = raw_extraction()
    reply["totals"]["gross_amount"] = "n/a"
    runs.append(logged_lines(FakeGemini(reply=reply)))

    text = "\n".join(json.dumps(line) for lines in runs for line in lines)
    content = [
        *SENSITIVE_VALUES,
        "51109301",
        "03/07/2023",
        "Widget",
        "74,120.00",
        "733,788.00",
        "Jane Roe",
        "TechVision",
        "1 Main Street",
        "27AAAAA0000A1Z5",
        "n/a",
    ]
    for value in content:
        assert value not in text, value
