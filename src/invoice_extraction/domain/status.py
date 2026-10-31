"""Job states shared by every layer."""

from dataclasses import dataclass
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

# A job in one of these states accepts no more work (a failed one only through redrive).
FINAL_STATUSES: frozenset[JobStatus] = frozenset(
    {JobStatus.SUCCEEDED, JobStatus.FAILED_VALIDATION, JobStatus.EXPIRED}
)


@dataclass(frozen=True)
class RetryPolicy:
    """How many times a message is delivered and how long it is hidden between tries."""

    max_receives: int = 5
    base_seconds: int = 30
    cap_seconds: int = 900

    def is_last(self, receive_count: int) -> bool:
        return receive_count >= self.max_receives

    def delay(self, receive_count: int) -> int:
        """Visibility delay after the given receive: doubles each time, up to the cap."""
        return min(self.cap_seconds, self.base_seconds * 2 ** (receive_count - 1))


@dataclass(frozen=True)
class Claim:
    """A conditional move into PROCESSING: allowed sources and required attributes."""

    expected: frozenset[JobStatus]
    requires: dict[str, str] | None = None
    reset: bool = False  # redrive: clear the previous failure before reprocessing


def claim_for(status: JobStatus) -> Claim | None:
    """The move that takes a job in `status` into PROCESSING, or None if it takes no work.

    A FAILED job is claimed only when it failed for an infrastructure reason
    (`retries_exhausted`); a business failure is never replayed.
    """
    if status in FINAL_STATUSES:
        return None
    if status == JobStatus.FAILED:
        return Claim(
            frozenset({JobStatus.FAILED}), requires={"failure_cause": RETRIES_EXHAUSTED}, reset=True
        )
    return Claim(transition_sources(JobStatus.PROCESSING) - {JobStatus.FAILED})


def transition_sources(target: JobStatus) -> frozenset[JobStatus]:
    """Statuses from which `target` may be entered."""
    return frozenset(s for s, targets in TRANSITIONS.items() if target in targets)


class IllegalTransitionError(Exception):
    """A conditional write found the job in a status the move is not allowed from."""
