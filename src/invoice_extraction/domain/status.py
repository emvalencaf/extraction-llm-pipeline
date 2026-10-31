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
