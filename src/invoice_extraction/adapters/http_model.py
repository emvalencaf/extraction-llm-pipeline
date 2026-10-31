"""ExtractionModel that calls an HTTP model service (the local `fake-gemini`)."""

import json
import urllib.request
from typing import Any


class HttpExtractionModel:
    def __init__(self, base_url: str, timeout: float = 60) -> None:
        self._url = base_url.rstrip("/") + "/extract"
        self._timeout = timeout

    def extract(self, text: str, schema: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            self._url,
            data=json.dumps({"text": text, "schema": schema}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self._timeout) as response:
            return json.loads(response.read())
