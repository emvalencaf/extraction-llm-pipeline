"""The pipeline use case: PDF in, validated Extraction or terminal status out."""

from dataclasses import dataclass, field

from pydantic import ValidationError

from invoice_extraction.application.ports import ExtractionModel, PdfTextReader, PdfUnreadableError
from invoice_extraction.domain.schema import Extraction, model_schema
from invoice_extraction.domain.status import JobStatus


@dataclass(frozen=True)
class PipelineResult:
    status: JobStatus
    extraction: Extraction | None = None
    errors: list[str] = field(default_factory=list)


class ExtractInvoice:
    def __init__(self, reader: PdfTextReader, model: ExtractionModel) -> None:
        self._reader = reader
        self._model = model

    def __call__(self, pdf: bytes) -> PipelineResult:
        try:
            text = self._reader.read(pdf)
        except PdfUnreadableError as error:
            return PipelineResult(JobStatus.FAILED, errors=[str(error)])
        raw = self._model.extract(text, model_schema())
        try:
            extraction = Extraction.model_validate(raw)
        except ValidationError as error:
            messages = [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors()]
            return PipelineResult(JobStatus.FAILED_VALIDATION, errors=messages)
        return PipelineResult(JobStatus.SUCCEEDED, extraction=extraction)
