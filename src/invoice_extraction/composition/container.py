"""Wire adapters into the pipeline use case."""

from collections.abc import Callable

from invoice_extraction.adapters.bundle_loader import load_bundle
from invoice_extraction.adapters.presidio_detector import PresidioDetector
from invoice_extraction.adapters.pypdf_reader import PypdfTextReader
from invoice_extraction.application.observability import EventSink
from invoice_extraction.application.pipeline import ExtractInvoice, RetryPolicy
from invoice_extraction.application.ports import ExtractionModel, SensitiveDetector
from invoice_extraction.application.post_slot import PostSlot
from invoice_extraction.application.pre_slot import PreSlot
from invoice_extraction.application.prompt_bundle import PromptBundle

_detector: SensitiveDetector | None = None


def _default_detector() -> SensitiveDetector:
    """Build the Presidio engine once per process: it is slow to construct and stateless."""
    global _detector
    if _detector is None:
        _detector = PresidioDetector()
    return _detector


def build_extract_invoice(
    model: ExtractionModel,
    detector: SensitiveDetector | None = None,
    *,
    bundle: PromptBundle | None = None,
    retry: RetryPolicy | None = None,
    max_repairs: int = 2,
    sleep: Callable[[float], None] | None = None,
    rng: Callable[[], float] | None = None,
    sink: EventSink | None = None,
) -> ExtractInvoice:
    reader = PypdfTextReader()
    pre = PreSlot(reader=reader, pages=reader, detector=detector or _default_detector())
    options = {}
    if sleep is not None:
        options["sleep"] = sleep
    if rng is not None:
        options["rng"] = rng
    return ExtractInvoice(
        pre=pre,
        model=model,
        post=PostSlot(),
        bundle=bundle or load_bundle(),
        retry=retry,
        sink=sink,
        max_repairs=max_repairs,
        **options,
    )
