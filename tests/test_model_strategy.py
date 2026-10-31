"""Seam 1: model strategy, repair loop, transient retries and the Prompt Bundle.

Everything runs against fake-gemini with model-targeted failure injection.
"""

import json
from pathlib import Path

import pytest

from invoice_extraction.adapters.bundle_loader import load_bundle
from invoice_extraction.adapters.fake_gemini import FakeGemini
from invoice_extraction.application.ports import (
    ModelRejectedError,
    ModelUnavailableError,
    TransientModelError,
)
from invoice_extraction.composition.container import build_extract_invoice
from invoice_extraction.domain.schema import Extraction
from invoice_extraction.domain.status import JobStatus, TerminalReason
from support.invoices import invoice_pdf, raw_extraction

BUNDLE = load_bundle()
PRIMARY, FALLBACK, ESCALATION = (
    BUNDLE.primary.name,
    BUNDLE.fallback.name,
    BUNDLE.escalation.name,
)
RATE_LIMITED = TransientModelError("429 rate limited")


def invalid() -> dict:
    reply = raw_extraction()
    reply["totals"]["gross_amount"] = "n/a"
    return reply


def run(model: FakeGemini, sleeps: list[float] | None = None):
    sleeps = [] if sleeps is None else sleeps
    extract = build_extract_invoice(model, sleep=sleeps.append, rng=lambda: 0.5)
    return extract(invoice_pdf())


# --- Prompt Bundle ---------------------------------------------------------------


def test_every_result_carries_the_prompt_bundle_hash():
    ok = run(FakeGemini(reply=raw_extraction()))
    bad = run(FakeGemini(reply=invalid()))
    unreadable = build_extract_invoice(FakeGemini(reply=raw_extraction()))(b"not a pdf")

    assert ok.prompt_version == bad.prompt_version == unreadable.prompt_version
    assert ok.prompt_version == BUNDLE.version
    assert len(BUNDLE.version) == 16


def test_prompt_version_is_a_content_hash():
    from dataclasses import replace

    changed = replace(BUNDLE, system_prompt=BUNDLE.system_prompt + " Be brief.")

    assert changed.version != BUNDLE.version
    assert replace(BUNDLE).version == BUNDLE.version


def test_few_shot_examples_come_only_from_the_train_set():
    manifest = json.loads(Path("data/split_manifest.json").read_text(encoding="utf-8"))
    train = {entry["invoice_no"] for entry in manifest["sets"]["train"]}

    assert BUNDLE.examples
    assert {example.invoice_no for example in BUNDLE.examples} <= train
    for example in BUNDLE.examples:
        Extraction.model_validate(example.extraction)


def test_model_request_carries_the_bundle_prompts_and_examples():
    model = FakeGemini(reply=raw_extraction())

    run(model)

    (request,) = model.calls
    assert request.model == PRIMARY
    assert request.system_prompt == BUNDLE.system_prompt
    assert len(request.examples) == len(BUNDLE.examples)
    assert request.temperature == 0
    assert request.repair is None


# --- Transient retries and fallback ------------------------------------------------


def test_transient_errors_are_retried_with_jittered_backoff():
    model = FakeGemini(reply=raw_extraction())
    model.inject(PRIMARY, RATE_LIMITED, times=2)
    sleeps: list[float] = []

    result = run(model, sleeps)

    assert result.status is JobStatus.SUCCEEDED
    assert model.models_called() == [PRIMARY] * 3
    assert len(sleeps) == 2
    assert 0 < sleeps[0] < sleeps[1]  # exponential cap, scaled by the jitter draw


def test_jitter_scales_the_delay():
    model = FakeGemini(reply=raw_extraction())
    model.inject(PRIMARY, RATE_LIMITED, times=1)
    low, high = [], []

    build_extract_invoice(model, sleep=low.append, rng=lambda: 0.1)(invoice_pdf())
    model2 = FakeGemini(reply=raw_extraction())
    model2.inject(PRIMARY, RATE_LIMITED, times=1)
    build_extract_invoice(model2, sleep=high.append, rng=lambda: 0.9)(invoice_pdf())

    assert low[0] < high[0]


def test_exhausted_retries_fall_back_to_the_fallback_model():
    model = FakeGemini(reply=raw_extraction())
    model.inject(PRIMARY, RATE_LIMITED)

    result = run(model)

    assert result.status is JobStatus.SUCCEEDED
    assert result.model == FALLBACK
    assert model.models_called()[-1] == FALLBACK
    assert ESCALATION not in model.models_called()


def test_rejected_request_falls_back_without_retrying():
    model = FakeGemini(reply=raw_extraction())
    model.inject(PRIMARY, ModelRejectedError("400 invalid argument"))
    sleeps: list[float] = []

    result = run(model, sleeps)

    assert result.model == FALLBACK
    assert model.models_called() == [PRIMARY, FALLBACK]
    assert sleeps == []


def test_all_models_unavailable_is_an_infrastructure_failure():
    model = FakeGemini(reply=raw_extraction())
    model.inject(PRIMARY, RATE_LIMITED)
    model.inject(FALLBACK, RATE_LIMITED)

    with pytest.raises(ModelUnavailableError):
        run(model)


# --- Repair loop and escalation ----------------------------------------------------


def test_validation_failure_is_repaired_with_the_errors_in_the_prompt():
    replies = iter([invalid(), raw_extraction()])
    model = FakeGemini(reply=lambda request: next(replies))

    result = run(model)

    assert result.status is JobStatus.SUCCEEDED
    first, second = model.calls
    assert first.repair is None
    assert second.repair is not None
    assert second.repair.instruction == BUNDLE.repair_prompt
    assert second.repair.previous["totals"]["gross_amount"] == "n/a"
    assert any("totals.gross_amount" in error for error in second.repair.errors)
    assert second.model == PRIMARY


def test_exhausted_repair_escalates_to_the_quality_model():
    model = FakeGemini(
        reply=lambda request: raw_extraction() if request.model == ESCALATION else invalid()
    )

    result = run(model)

    assert result.status is JobStatus.SUCCEEDED
    assert result.model == ESCALATION
    assert model.models_called() == [PRIMARY] * 3 + [ESCALATION]


def test_escalation_model_is_called_with_temperature_zero():
    model = FakeGemini(
        reply=lambda request: raw_extraction() if request.model == ESCALATION else invalid()
    )

    run(model)

    assert model.calls[-1].model == ESCALATION
    assert model.calls[-1].temperature == 0


def test_exhausted_repair_and_escalation_ends_as_failed_validation():
    model = FakeGemini(reply=invalid())

    result = run(model)

    assert result.status is JobStatus.FAILED_VALIDATION
    assert result.reason is TerminalReason.SCHEMA_INVALID
    assert result.extraction is None
    assert any("totals.gross_amount" in error for error in result.errors)
    assert model.models_called() == [PRIMARY] * 3 + [ESCALATION] * 3


def test_unavailable_escalation_model_ends_as_failed_validation():
    model = FakeGemini(reply=invalid())
    model.inject(ESCALATION, RATE_LIMITED)

    result = run(model)

    assert result.status is JobStatus.FAILED_VALIDATION
    assert result.reason is TerminalReason.SCHEMA_INVALID


def test_no_langgraph_checkpointer_is_used():
    extract = build_extract_invoice(FakeGemini(reply=raw_extraction()))

    assert extract.graph.checkpointer is None
