"""The Gemini adapter, driven through a stub client: no live Gemini calls."""

import json
from types import SimpleNamespace

import pytest
from google.genai import errors

from invoice_extraction.adapters.gemini import GeminiExtractionModel
from invoice_extraction.application.ports import (
    Example,
    ExtractionRequest,
    ModelRejectedError,
    Repair,
    TransientModelError,
)
from support.invoices import raw_extraction


class StubClient:
    """Mimics `client.models.generate_content`; records what it was sent."""

    def __init__(self, text: str | None = None, error: Exception | None = None) -> None:
        self.sent: list[dict] = []
        self._text = json.dumps(raw_extraction()) if text is None else text
        self._error = error
        self.models = SimpleNamespace(generate_content=self._generate)

    def _generate(self, *, model, contents, config):
        self.sent.append({"model": model, "contents": contents, "config": config})
        if self._error:
            raise self._error
        usage = SimpleNamespace(prompt_token_count=11, candidates_token_count=7)
        return SimpleNamespace(text=self._text, usage_metadata=usage)


def request(**changes) -> ExtractionRequest:
    base = {
        "model": "gemini-3.5-flash-lite",
        "text": "invoice text",
        "schema": {"type": "object"},
        "system_prompt": "extract",
        "examples": (Example("example text", {"invoice_no": "1"}),),
        "temperature": 0,
    }
    return ExtractionRequest(**{**base, **changes})


def test_returns_the_json_the_model_produced():
    assert GeminiExtractionModel(StubClient()).extract(request()).data == raw_extraction()


def test_reports_the_token_usage_of_the_call():
    reply = GeminiExtractionModel(StubClient()).extract(request())

    assert (reply.input_tokens, reply.output_tokens) == (11, 7)


def test_sends_prompt_schema_examples_and_text():
    client = StubClient()

    GeminiExtractionModel(client).extract(request())

    (sent,) = client.sent
    assert sent["model"] == "gemini-3.5-flash-lite"
    assert sent["config"].system_instruction == "extract"
    assert sent["config"].response_mime_type == "application/json"
    assert sent["config"].response_json_schema == {"type": "object"}
    turns = [(c.role, c.parts[0].text) for c in sent["contents"]]
    assert turns == [
        ("user", "example text"),
        ("model", '{"invoice_no": "1"}'),
        ("user", "invoice text"),
    ]


def test_temperature_is_omitted_when_the_model_does_not_support_it():
    with_temp, without = StubClient(), StubClient()

    GeminiExtractionModel(with_temp).extract(request(temperature=0))
    GeminiExtractionModel(without).extract(request(temperature=None))

    assert with_temp.sent[0]["config"].temperature == 0
    assert without.sent[0]["config"].temperature is None


def test_repair_replays_the_previous_answer_and_the_errors():
    client = StubClient()
    repair = Repair("fix it", {"invoice_no": "x"}, ("totals.gross_amount: bad",))

    GeminiExtractionModel(client).extract(request(examples=(), repair=repair))

    turns = [(c.role, c.parts[0].text) for c in client.sent[0]["contents"]]
    assert turns[0] == ("user", "invoice text")
    assert turns[1] == ("model", '{"invoice_no": "x"}')
    assert turns[2][0] == "user"
    assert "fix it" in turns[2][1]
    assert "totals.gross_amount: bad" in turns[2][1]


@pytest.mark.parametrize("code", [429, 500, 503, 504])
def test_rate_limits_and_server_errors_are_transient(code):
    client = StubClient(error=errors.APIError(code, {"error": {"message": "x"}}))

    with pytest.raises(TransientModelError):
        GeminiExtractionModel(client).extract(request())


@pytest.mark.parametrize("code", [400, 403, 404])
def test_client_errors_are_not_retryable(code):
    client = StubClient(error=errors.APIError(code, {"error": {"message": "x"}}))

    with pytest.raises(ModelRejectedError):
        GeminiExtractionModel(client).extract(request())


def test_unparseable_reply_is_transient():
    with pytest.raises(TransientModelError):
        GeminiExtractionModel(StubClient(text="not json")).extract(request())
