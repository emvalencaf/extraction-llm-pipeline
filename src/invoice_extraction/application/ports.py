"""Ports the use cases depend on; adapters implement them."""

from collections.abc import Collection
from dataclasses import dataclass
from typing import Any, Protocol

from invoice_extraction.domain.job import Job, JobUpdate
from invoice_extraction.domain.status import JobStatus


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


class JobRepository(Protocol):
    def create(self, job: Job) -> None: ...

    def get(self, job_id: str) -> Job | None: ...

    def transition(
        self,
        job_id: str,
        to: JobStatus,
        *,
        expected: Collection[JobStatus],
        requires: dict[str, str] | None = None,
        update: JobUpdate | None = None,
    ) -> None:
        """Move the job to status `to` only if its status is in `expected` (and every
        `requires` attribute matches); otherwise raise IllegalTransitionError."""

    def claim_idempotency_key(self, key: str, job_id: str) -> str:
        """Bind `key` to `job_id` once. Return the job id bound to the key (the given one
        when this call won, the earlier one when the key was already used)."""

    def discard(self, job_id: str) -> None:
        """Delete a job created but never handed out."""


class QueueDelayer(Protocol):
    def delay(self, receipt_handle: str, seconds: int) -> None:
        """Hide the message from the queue for `seconds` before its next delivery."""


class BlobStore(Protocol):
    def presign_put(self, key: str) -> str:
        """URL the client PUTs the PDF to."""

    def get(self, key: str) -> bytes:
        """Return the object body; raise BlobNotFoundError if absent."""

    def size(self, key: str) -> int:
        """Return the object size in bytes; raise BlobNotFoundError if absent."""


class BlobNotFoundError(Exception):
    """The uploaded object is not in the store."""


class TransientModelError(Exception):
    """A short-lived model failure (rate limit, overload); retry may succeed."""


class ModelRejectedError(Exception):
    """The model refused the request; retrying the same model is pointless."""


class ModelUnavailableError(Exception):
    """No configured model could answer; an infrastructure failure, not a business one.

    The queue redelivers the job later with a growing visibility delay.
    """
