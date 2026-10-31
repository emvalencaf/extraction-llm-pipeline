"""In-process fake-gemini: an ExtractionModel that returns canned replies.

Test seam 1 uses it instead of the Gemini API. `inject` makes calls to one model name
fail (model-targeted failure injection) so fallback and escalation can be exercised.
Keep it importable and dependency free.
"""

from collections.abc import Callable
from typing import Any

from invoice_extraction.application.ports import ExtractionRequest

Reply = dict[str, Any] | Callable[[ExtractionRequest], dict[str, Any]]


class FakeGemini:
    def __init__(self, reply: Reply) -> None:
        self._reply = reply
        self._failures: dict[str, tuple[Exception, int | None]] = {}
        self.calls: list[ExtractionRequest] = []

    def inject(self, model: str, error: Exception, times: int | None = None) -> None:
        """Raise `error` on calls to `model`: `times` calls, or every call when None."""
        self._failures[model] = (error, times)

    def extract(self, request: ExtractionRequest) -> dict[str, Any]:
        self.calls.append(request)
        failure = self._failures.get(request.model)
        if failure is not None:
            error, times = failure
            if times is None:
                raise error
            if times > 0:
                self._failures[request.model] = (error, times - 1)
                raise error
        return self._reply(request) if callable(self._reply) else self._reply

    def models_called(self) -> list[str]:
        return [call.model for call in self.calls]
