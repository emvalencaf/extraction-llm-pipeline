"""The job record and the fields a status change may set."""

from dataclasses import dataclass, field
from typing import Any

from invoice_extraction.domain.status import JobStatus


@dataclass(frozen=True)
class Job:
    """One uploaded invoice moving through the lifecycle."""

    job_id: str
    status: JobStatus
    key: str
    created_at: int = 0
    errors: list[str] = field(default_factory=list)
    reason: str | None = None
    result: dict[str, Any] | None = None
    failure_cause: str | None = None


@dataclass(frozen=True)
class JobUpdate:
    """Fields written together with a status change; None leaves a field untouched."""

    errors: list[str] | None = None
    reason: str | None = None
    result: dict[str, Any] | None = None
    failure_cause: str | None = None
