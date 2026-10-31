"""Ports the use cases depend on; adapters implement them."""

from dataclasses import dataclass
from typing import Any, Protocol


class PdfTextReader(Protocol):
    def read(self, pdf: bytes) -> str:
        """Return the text of a PDF; raise PdfUnreadableError if it cannot be read."""


class PdfPageCounter(Protocol):
    def page_count(self, pdf: bytes) -> int:
        """Return the number of pages; raise PdfUnreadableError if it cannot be read."""


@dataclass(frozen=True)
class SensitiveSpan:
    """A sensitive value found in a text: [start, end) of kind `kind` (NAME, ADDRESS, ...)."""

    start: int
    end: int
    kind: str


class SensitiveDetector(Protocol):
    def detect(self, text: str) -> list[SensitiveSpan]:
        """Return the spans of sensitive values in `text` (may overlap; caller resolves)."""


@dataclass(frozen=True)
class Example:
    """One few-shot example: invoice text and the Extraction it should produce."""

    text: str
    extraction: dict[str, Any]


@dataclass(frozen=True)
class Repair:
    """Context for re-asking after a validation failure."""

    instruction: str
    previous: dict[str, Any]
    errors: tuple[str, ...]


@dataclass(frozen=True)
class ExtractionRequest:
    model: str
    text: str
    schema: dict[str, Any]
    system_prompt: str
    examples: tuple[Example, ...] = ()
    # None means "do not send": newer Gemini models reject the parameter
    temperature: float | None = None
    repair: Repair | None = None


@dataclass(frozen=True)
class ModelReply:
    """What a model call returned: the raw data and the token usage it reports."""

    data: dict[str, Any]
    input_tokens: int | None = None
    output_tokens: int | None = None


class ExtractionModel(Protocol):
    def extract(self, request: ExtractionRequest) -> ModelReply:
        """Return the raw (unvalidated) Extraction the model produced, with token usage.

        Raise TransientModelError for retryable failures (429, 5xx) and
        ModelRejectedError for failures a retry cannot fix.
        """


class PdfUnreadableError(Exception):
    """The input is not a PDF the pipeline can read."""


class TransientModelError(Exception):
    """A short-lived model failure (rate limit, overload); retry may succeed."""


class ModelRejectedError(Exception):
    """The model refused the request; retrying the same model is pointless."""


class ModelUnavailableError(Exception):
    """No configured model could answer; an infrastructure failure, not a business one.

    The queue redelivers the job later with a growing visibility delay.
    """
