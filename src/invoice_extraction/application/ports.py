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


class JobRepository(Protocol):
    def create(self, job: dict[str, Any]) -> None: ...

    def get(self, job_id: str) -> dict[str, Any] | None: ...

    def update(self, job_id: str, **fields: Any) -> None: ...


class BlobStore(Protocol):
    def presign_put(self, key: str) -> str:
        """URL the client PUTs the PDF to."""

    def get(self, key: str) -> bytes:
        """Return the object body; raise BlobNotFoundError if absent."""


class BlobNotFoundError(Exception):
    """The uploaded object is not in the store."""
