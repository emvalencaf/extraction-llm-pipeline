"""The outcome of one pipeline run, kept apart from the pipeline so job handling stays light."""

from dataclasses import dataclass, field

from invoice_extraction.application.grounding import GroundingRate
from invoice_extraction.domain.schema import Extraction
from invoice_extraction.domain.status import JobStatus, TerminalReason


@dataclass(frozen=True)
class PipelineResult:
    status: JobStatus
    extraction: Extraction | None = None
    errors: list[str] = field(default_factory=list)
    reason: TerminalReason | None = None
    prompt_version: str | None = None
    model: str | None = None
    grounding: GroundingRate | None = None  # informational; never blocks
