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
