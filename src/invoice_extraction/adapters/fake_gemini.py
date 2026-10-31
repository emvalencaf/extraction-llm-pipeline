"""In-process fake-gemini: an ExtractionModel that returns canned replies.

Test seam 1 uses it instead of the Gemini API. Later tickets extend it with failure
injection (errors, per-model behavior); keep it importable and dependency free.
"""

from collections.abc import Callable
from typing import Any

Reply = dict[str, Any] | Callable[[str], dict[str, Any]]


class FakeGemini:
    def __init__(self, reply: Reply) -> None:
        self._reply = reply
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def extract(self, text: str, schema: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((text, schema))
        return self._reply(text) if callable(self._reply) else self._reply
