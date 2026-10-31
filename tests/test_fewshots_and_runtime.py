"""Seam 1 and 2: the shipped few-shots carry no raw identifiers; the runtime picks the model."""

import json
from importlib import resources

import pytest

from invoice_extraction.adapters.bundle_loader import load_bundle
from invoice_extraction.adapters.gemini import GeminiExtractionModel
from invoice_extraction.adapters.http_model import HttpExtractionModel
from invoice_extraction.adapters.presidio_detector import PresidioDetector
from invoice_extraction.application.privacy import TOKEN
from invoice_extraction.composition.runtime import build_model, resolve_gemini_key

# Prompt Version of the bundle when the few-shots still held raw identifiers
RAW_EXAMPLES_VERSION = "ec57dba25d195f0d"


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)


@pytest.fixture(scope="module")
def examples():
    path = resources.files("invoice_extraction") / "prompts" / "examples.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_fewshots_contain_no_identifier_the_detector_finds(examples):
    detector = PresidioDetector()
    leaks = []
    for example in examples:
        for text in [example["text"], *strings(example["extraction"])]:
            leaks += [text[s.start : s.end] for s in detector.detect(text)]
    assert leaks == []


def test_fewshots_use_the_same_placeholder_form_as_real_inputs(examples):
    for example in examples:
        assert TOKEN.search(example["text"])
        parties = (example["extraction"]["seller"], example["extraction"]["client"])
        for party in parties:
            assert TOKEN.fullmatch(party["name"]) and TOKEN.fullmatch(party["tax_id"])
        # every token the model must emit appears in the example text
        text_tokens = {m.group(0) for m in TOKEN.finditer(example["text"])}
        out_tokens = {m.group(0) for s in strings(example["extraction"]) for m in TOKEN.finditer(s)}
        assert out_tokens <= text_tokens


def test_prompt_version_changed_with_the_anonymized_fewshots():
    assert load_bundle().version != RAW_EXAMPLES_VERSION


def test_every_model_runs_at_temperature_zero():
    bundle = load_bundle()
    assert [bundle.primary.temperature, bundle.fallback.temperature] == [0, 0]
    assert bundle.escalation.temperature == 0


def test_runtime_uses_gemini_when_the_api_key_is_set(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("FAKE_GEMINI_URL", raising=False)
    assert isinstance(build_model(), GeminiExtractionModel)


def test_gemini_key_is_read_from_ssm_when_only_the_parameter_name_is_set(monkeypatch):
    class FakeSsm:
        def get_parameter(self, **kwargs):
            assert kwargs == {"Name": "/invoice/gemini", "WithDecryption": True}
            return {"Parameter": {"Value": "key-from-ssm"}}

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY_SSM_PARAMETER", "/invoice/gemini")

    assert resolve_gemini_key(ssm=FakeSsm()) == "key-from-ssm"


def test_a_plain_gemini_key_wins_over_the_ssm_parameter(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "plain")
    monkeypatch.setenv("GEMINI_API_KEY_SSM_PARAMETER", "/invoice/gemini")

    assert resolve_gemini_key(ssm=None) == "plain"


def test_no_gemini_key_configured_resolves_to_none(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY_SSM_PARAMETER", raising=False)

    assert resolve_gemini_key(ssm=None) is None


def test_runtime_falls_back_to_the_fake_gemini_url(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("FAKE_GEMINI_URL", "http://fake-gemini:8000")
    assert isinstance(build_model(), HttpExtractionModel)
