"""The pipeline use case: PDF in, validated Extraction or terminal status out."""

from dataclasses import dataclass, field

from pydantic import ValidationError

from invoice_extraction.application.ports import ExtractionModel
from invoice_extraction.application.post_slot import PostSlot
from invoice_extraction.application.pre_slot import PreSlot, RejectedError
from invoice_extraction.domain.schema import Extraction, model_schema
from invoice_extraction.domain.status import JobStatus, TerminalReason


@dataclass(frozen=True)
class PipelineResult:
    status: JobStatus
    extraction: Extraction | None = None
    errors: list[str] = field(default_factory=list)
    reason: TerminalReason | None = None


class ExtractInvoice:
    def __init__(self, pre: PreSlot, model: ExtractionModel, post: PostSlot) -> None:
        self._pre = pre
        self._model = model
        self._post = post

    def __call__(self, pdf: bytes) -> PipelineResult:
        try:
            prepared = self._pre(pdf)
        except RejectedError as rejected:
            return PipelineResult(JobStatus.FAILED, errors=[str(rejected)], reason=rejected.reason)
        raw = self._model.extract(prepared.text, model_schema())
        try:
            restored = self._post(raw, prepared.placeholders)
        except RejectedError as rejected:
            return PipelineResult(
                JobStatus.FAILED_VALIDATION, errors=[str(rejected)], reason=rejected.reason
            )
        try:
            extraction = Extraction.model_validate(restored)
        except ValidationError as error:
            messages = [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors()]
            return PipelineResult(
                JobStatus.FAILED_VALIDATION, errors=messages, reason=TerminalReason.SCHEMA_INVALID
            )
        return PipelineResult(JobStatus.SUCCEEDED, extraction=extraction)
