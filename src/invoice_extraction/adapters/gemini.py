"""ExtractionModel backed by the Gemini API (google-genai)."""

import json
from typing import Any

from google.genai import errors, types

from invoice_extraction.application.ports import (
    ExtractionRequest,
    ModelRejectedError,
    ModelReply,
    TransientModelError,
)

_TRANSIENT_CODES = {429, 500, 502, 503, 504}


def _turn(role: str, text: str) -> types.Content:
    return types.Content(role=role, parts=[types.Part(text=text)])


def _contents(request: ExtractionRequest) -> list[types.Content]:
    contents: list[types.Content] = []
    for example in request.examples:
        contents.append(_turn("user", example.text))
        contents.append(_turn("model", json.dumps(example.extraction)))
    contents.append(_turn("user", request.text))
    if request.repair is not None:
        problems = "\n".join(f"- {error}" for error in request.repair.errors)
        contents.append(_turn("model", json.dumps(request.repair.previous)))
        contents.append(_turn("user", f"{request.repair.instruction}\n\nProblems:\n{problems}"))
    return contents


class GeminiExtractionModel:
    """`client` is a `google.genai.Client` (or anything with `models.generate_content`)."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def extract(self, request: ExtractionRequest) -> ModelReply:
        config = types.GenerateContentConfig(
            system_instruction=request.system_prompt,
            response_mime_type="application/json",
            response_json_schema=request.schema,
            # newer models reject temperature; the Prompt Bundle sets None for them
            temperature=request.temperature,
        )
        try:
            response = self._client.models.generate_content(
                model=request.model, contents=_contents(request), config=config
            )
        except errors.APIError as error:
            if error.code in _TRANSIENT_CODES:
                raise TransientModelError(f"{error.code}: {error}") from error
            raise ModelRejectedError(f"{error.code}: {error}") from error
        usage = getattr(response, "usage_metadata", None)
        try:
            data = json.loads(response.text)
        except (TypeError, ValueError) as error:
            raise TransientModelError("model reply was not valid JSON") from error
        return ModelReply(
            data,
            input_tokens=getattr(usage, "prompt_token_count", None),
            output_tokens=getattr(usage, "candidates_token_count", None),
        )
