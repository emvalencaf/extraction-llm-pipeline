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


class ExtractionModel(Protocol):
    def extract(self, text: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Return the raw (unvalidated) Extraction the model produced for `text`."""


class PdfUnreadableError(Exception):
    """The input is not a PDF the pipeline can read."""
