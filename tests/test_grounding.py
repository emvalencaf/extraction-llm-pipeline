"""Seam 1: the Grounding Rate in the result (informational, non-anonymized fields only)."""

from invoice_extraction.adapters.fake_gemini import FakeGemini
from invoice_extraction.composition.container import build_extract_invoice
from invoice_extraction.domain.status import JobStatus
from support.invoices import invoice_pdf, raw_extraction


def run(reply: dict):
    return build_extract_invoice(FakeGemini(reply=reply))(invoice_pdf())


def test_result_reports_which_non_anonymized_fields_are_found_in_the_document():
    result = run(raw_extraction())

    assert result.status is JobStatus.SUCCEEDED
    grounding = result.grounding
    # currency and totals.vat_amount are not printed in the sample PDF
    assert grounding.total == 14
    assert grounding.grounded == 12
    assert grounding.ungrounded == ("currency", "totals.vat_amount")
    assert grounding.rate == 12 / 14


def test_a_hallucinated_value_lowers_the_rate_but_never_blocks_the_job():
    reply = raw_extraction()
    reply["items"][0]["description"] = "Gadget"
    reply["items"][0]["unit_price"] = "99,999.00"

    result = run(reply)

    assert result.status is JobStatus.SUCCEEDED
    assert result.extraction is not None
    assert result.grounding.grounded == 10
    assert "items[0].description" in result.grounding.ungrounded
    assert "items[0].unit_price" in result.grounding.ungrounded


def test_anonymized_fields_are_not_part_of_the_rate():
    reply = raw_extraction()
    reply["seller"]["address"] = "an address that is nowhere in the document"
    reply["client"]["name"] = "Jane Roe"

    result = run(reply)

    assert result.grounding.total == 14
    assert not any(p.startswith(("seller", "client")) for p in result.grounding.ungrounded)


def test_a_failed_job_has_no_grounding_rate():
    reply = raw_extraction()
    reply["totals"]["gross_amount"] = "n/a"

    result = run(reply)

    assert result.status is JobStatus.FAILED_VALIDATION
    assert result.grounding is None


def test_amount_formatted_differently_from_the_document_is_still_grounded():
    reply = raw_extraction()
    reply["items"][0]["unit_price"] = "74120.00"

    result = run(reply)

    assert "items[0].unit_price" not in result.grounding.ungrounded
