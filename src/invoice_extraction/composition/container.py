"""Wire adapters into the pipeline use case."""

from invoice_extraction.adapters.presidio_detector import PresidioDetector
from invoice_extraction.adapters.pypdf_reader import PypdfTextReader
from invoice_extraction.application.pipeline import ExtractInvoice
from invoice_extraction.application.ports import ExtractionModel, SensitiveDetector
from invoice_extraction.application.post_slot import PostSlot
from invoice_extraction.application.pre_slot import PreSlot

_detector: SensitiveDetector | None = None


def _default_detector() -> SensitiveDetector:
    """Build the Presidio engine once per process: it is slow to construct and stateless."""
    global _detector
    if _detector is None:
        _detector = PresidioDetector()
    return _detector


def build_extract_invoice(
    model: ExtractionModel, detector: SensitiveDetector | None = None
) -> ExtractInvoice:
    reader = PypdfTextReader()
    pre = PreSlot(reader=reader, pages=reader, detector=detector or _default_detector())
    return ExtractInvoice(pre=pre, model=model, post=PostSlot())
