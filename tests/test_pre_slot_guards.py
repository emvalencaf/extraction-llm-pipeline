"""Seam 1 (pre slot): PDF guards end the job with a clear terminal reason."""

from invoice_extraction.adapters.fake_gemini import FakeGemini
from invoice_extraction.composition.container import build_extract_invoice
from invoice_extraction.domain.status import JobStatus, TerminalReason
from support.invoices import INVOICE_LINES, raw_extraction
from support.pdf import make_pdf

MB = 1024 * 1024


def test_pdf_over_5_mb_is_rejected_before_the_model():
    model = FakeGemini(reply=raw_extraction())
    pdf = make_pdf(INVOICE_LINES) + b"%" + b"x" * (5 * MB)

    result = build_extract_invoice(model)(pdf)

    assert result.status is JobStatus.FAILED
    assert result.reason is TerminalReason.PDF_TOO_LARGE
    assert model.calls == []


def test_pdf_over_10_pages_is_rejected_before_the_model():
    model = FakeGemini(reply=raw_extraction())

    result = build_extract_invoice(model)(make_pdf(INVOICE_LINES, pages=11))

    assert result.status is JobStatus.FAILED
    assert result.reason is TerminalReason.PDF_TOO_LONG
    assert model.calls == []


def test_pdf_at_the_limits_is_accepted():
    model = FakeGemini(reply=raw_extraction())

    result = build_extract_invoice(model)(make_pdf(INVOICE_LINES, pages=10))

    assert result.status is JobStatus.SUCCEEDED


def test_unreadable_input_has_its_own_reason():
    result = build_extract_invoice(FakeGemini(reply=raw_extraction()))(b"not a pdf")

    assert result.reason is TerminalReason.PDF_UNREADABLE
