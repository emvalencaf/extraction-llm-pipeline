"""Ports the use cases depend on; adapters implement them."""

from typing import Any, Protocol


class PdfTextReader(Protocol):
    def read(self, pdf: bytes) -> str:
        """Return the text of a PDF; raise PdfUnreadableError if it cannot be read."""


class ExtractionModel(Protocol):
    def extract(self, text: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Return the raw (unvalidated) Extraction the model produced for `text`."""


class PdfUnreadableError(Exception):
    """The input is not a PDF the pipeline can read."""
