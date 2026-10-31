"""Wire adapters into the pipeline use case."""

from invoice_extraction.adapters.pypdf_reader import PypdfTextReader
from invoice_extraction.application.pipeline import ExtractInvoice
from invoice_extraction.application.ports import ExtractionModel


def build_extract_invoice(model: ExtractionModel) -> ExtractInvoice:
    return ExtractInvoice(reader=PypdfTextReader(), model=model)
