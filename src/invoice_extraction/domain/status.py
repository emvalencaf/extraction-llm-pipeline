"""Job states shared by every layer."""

from enum import StrEnum


class JobStatus(StrEnum):
    AWAITING_UPLOAD = "awaiting_upload"
    QUEUED = "queued"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED_VALIDATION = "failed_validation"
    FAILED = "failed"
    EXPIRED = "expired"


class TerminalReason(StrEnum):
    """Why a job ended without an Extraction, in terms a caller can act on."""

    PDF_TOO_LARGE = "pdf_too_large"
    PDF_TOO_LONG = "pdf_too_long"
    PDF_UNREADABLE = "pdf_unreadable"
    OUTPUT_REJECTED = "output_rejected"
    SCHEMA_INVALID = "schema_invalid"


MAX_PDF_BYTES = 5 * 1024 * 1024
MAX_PDF_PAGES = 10

# Legal moves. Writes are conditional on the current status being one of the sources, so a
# duplicate or late delivery cannot move a job somewhere it must not go.
# FAILED -> PROCESSING exists only for redrive: the service allows it solely when the failure
# cause was `retries_exhausted` (an infrastructure failure), never for a business failure.
TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.AWAITING_UPLOAD: frozenset(
        {JobStatus.QUEUED, JobStatus.PROCESSING, JobStatus.EXPIRED}
    ),
    JobStatus.QUEUED: frozenset({JobStatus.PROCESSING, JobStatus.FAILED}),
    JobStatus.PROCESSING: frozenset(
        {
            JobStatus.QUEUED,
            JobStatus.PROCESSING,
            JobStatus.SUCCEEDED,
            JobStatus.FAILED_VALIDATION,
            JobStatus.FAILED,
        }
    ),
    JobStatus.FAILED: frozenset({JobStatus.PROCESSING}),
    JobStatus.SUCCEEDED: frozenset(),
    JobStatus.FAILED_VALIDATION: frozenset(),
    JobStatus.EXPIRED: frozenset(),
}

RETRIES_EXHAUSTED = "retries_exhausted"
UPLOAD_TTL_SECONDS = 15 * 60


def transition_sources(target: JobStatus) -> frozenset[JobStatus]:
    """Statuses from which `target` may be entered."""
    return frozenset(s for s, targets in TRANSITIONS.items() if target in targets)


class IllegalTransitionError(Exception):
    """A conditional write found the job in a status the move is not allowed from."""
