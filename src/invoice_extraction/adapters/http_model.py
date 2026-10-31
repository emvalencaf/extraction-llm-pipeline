"""ExtractionModel that calls an HTTP model service (the local `fake-gemini`)."""

import json
import urllib.request

from invoice_extraction.application.ports import ExtractionRequest, ModelReply, TransientModelError


class HttpExtractionModel:
    def __init__(self, base_url: str, timeout: float = 60) -> None:
        self._url = base_url.rstrip("/") + "/extract"
        self._timeout = timeout

    def extract(self, request: ExtractionRequest) -> ModelReply:
        http_request = urllib.request.Request(
            self._url,
            data=json.dumps(
                {"model": request.model, "text": request.text, "schema": request.schema}
            ).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(http_request, timeout=self._timeout) as response:
                return ModelReply(json.loads(response.read()))
        except (OSError, ValueError) as error:
            raise TransientModelError(str(error)) from error
