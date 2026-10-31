"""Seam 1: the pipeline use case, driven with fake adapters and fake-gemini."""

from datetime import date
from decimal import Decimal

from invoice_extraction.adapters.fake_gemini import FakeGemini
from invoice_extraction.composition.container import build_extract_invoice
from invoice_extraction.domain.status import JobStatus
from support.invoices import invoice_pdf, raw_extraction


def test_valid_pdf_returns_a_normalized_extraction():
    extract = build_extract_invoice(FakeGemini(reply=raw_extraction()))

    result = extract(invoice_pdf())

    assert result.status is JobStatus.SUCCEEDED
    invoice = result.extraction
    assert invoice.issue_date == date(2023, 7, 3)
    assert invoice.items[0].unit_price == Decimal("74120.00")
    assert invoice.items[0].vat_pct == Decimal("10")
    assert invoice.totals.gross_amount == Decimal("733788.00")


def test_model_receives_the_pdf_text_and_a_schema_covering_every_field():
    model = FakeGemini(reply=raw_extraction())

    build_extract_invoice(model)(invoice_pdf())

    ((text, schema),) = model.calls
    assert "51109301" in text
    assert set(schema["properties"]) == set(raw_extraction())
    assert "tax_id" in schema["$defs"]["Party"]["properties"]


def test_unparseable_amount_is_a_terminal_validation_failure():
    reply = raw_extraction()
    reply["totals"]["gross_amount"] = "n/a"

    result = build_extract_invoice(FakeGemini(reply=reply))(invoice_pdf())

    assert result.status is JobStatus.FAILED_VALIDATION
    assert result.extraction is None
    assert any("totals.gross_amount" in error for error in result.errors)


def test_duplicate_fields_for_one_fact_are_rejected():
    reply = raw_extraction()
    reply["seller"]["gstin"] = reply["seller"]["tax_id"]

    result = build_extract_invoice(FakeGemini(reply=reply))(invoice_pdf())

    assert result.status is JobStatus.FAILED_VALIDATION


def test_non_pdf_input_fails_without_calling_the_model():
    model = FakeGemini(reply=raw_extraction())

    result = build_extract_invoice(model)(b"not a pdf")

    assert result.status is JobStatus.FAILED
    assert model.calls == []
