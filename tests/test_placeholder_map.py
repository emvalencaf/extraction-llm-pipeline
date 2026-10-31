"""The Placeholder map is in-memory only: never persisted, never printed."""

import copy
import json
import pickle

import pytest

from invoice_extraction.adapters.fake_gemini import FakeGemini
from invoice_extraction.application.ports import SensitiveSpan
from invoice_extraction.application.privacy import anonymize
from invoice_extraction.composition.container import build_extract_invoice
from support.invoices import raw_extraction
from support.pdf import make_pdf

SECRET = "Jane Roe"


def test_one_placeholder_per_distinct_value_numbered_by_first_appearance():
    text = "Jane Roe, John Doe, Jane Roe"
    spans = [
        SensitiveSpan(0, 8, "NAME"),
        SensitiveSpan(10, 18, "NAME"),
        SensitiveSpan(20, 28, "NAME"),
    ]

    anonymized, _ = anonymize(text, spans)

    assert anonymized == "[NAME_1], [NAME_2], [NAME_1]"


def test_map_hides_values_in_repr_and_str():
    _, placeholders = anonymize(SECRET, [SensitiveSpan(0, 8, "NAME")])

    assert SECRET not in repr(placeholders)
    assert SECRET not in str(placeholders)
    assert SECRET not in f"{placeholders!r}"


def test_map_cannot_be_pickled_copied_or_json_serialized():
    _, placeholders = anonymize(SECRET, [SensitiveSpan(0, 8, "NAME")])

    with pytest.raises(TypeError):
        pickle.dumps(placeholders)
    with pytest.raises(TypeError):
        copy.deepcopy(placeholders)
    with pytest.raises(TypeError):
        json.dumps(placeholders)


def test_pipeline_does_not_log_sensitive_values(caplog):
    caplog.set_level("DEBUG")
    lines = ["Invoice no: 1", "Client: Raj Electronics Pvt Ltd"]

    build_extract_invoice(FakeGemini(reply=raw_extraction()))(make_pdf(lines))

    assert "Raj Electronics" not in caplog.text


def test_model_receives_cleaned_text():
    model = FakeGemini(reply=raw_extraction())

    build_extract_invoice(model)(make_pdf(["Invoice   no:\t1", "", "Total   5"]))

    (request,) = model.calls
    assert request.text == "Invoice no: 1\nTotal 5"
