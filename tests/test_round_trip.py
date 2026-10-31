"""Seam 1: identifiers are anonymized before the model call and restored after it."""

from invoice_extraction.adapters.fake_gemini import FakeGemini
from invoice_extraction.composition.container import build_extract_invoice
from invoice_extraction.domain.status import JobStatus, TerminalReason
from support.invoices import SENSITIVE_VALUES, TWO_COLUMN_TEXT, leak_rate
from support.pdf import make_pdf


def pdf_of(text: str) -> bytes:
    return make_pdf(text.splitlines())


def copying_reply(text: str, overrides: dict | None = None) -> dict:
    """What a faithful model returns: Placeholders copied from the text into the fields."""
    lines = text.splitlines()
    seller_name, client_name = lines[3].split(" ")  # "[NAME_1] [NAME_2]"
    street_s, street_c = lines[4].split(" ")
    city_s, city_c = lines[5].split(" ")
    out = {
        "invoice_no": "51109301",
        "issue_date": "03/07/2023",
        "currency": "INR",
        "seller": {
            "name": seller_name,
            "address": f"{street_s}, {city_s}",
            "tax_id": "[TAX_ID_1]",
        },
        "client": {
            "name": client_name,
            "address": f"{street_c}, {city_c}",
            "tax_id": "[TAX_ID_2]",
        },
        "items": [],
        "totals": {"vat_pct": "10%", "net_amount": "1", "vat_amount": "1", "gross_amount": "1"},
    }
    for path, value in (overrides or {}).items():
        node = out
        *parents, leaf = path.split(".")
        for key in parents:
            node = node[key]
        node[leaf] = value
    return out


def model(**overrides) -> FakeGemini:
    return FakeGemini(reply=lambda text: copying_reply(text, overrides))


def test_model_never_sees_a_sensitive_value():
    fake = model()

    build_extract_invoice(fake)(pdf_of(TWO_COLUMN_TEXT))

    ((seen, _),) = fake.calls
    assert leak_rate([(seen, SENSITIVE_VALUES)]) == 0.0


def test_placeholders_are_restored_into_the_extraction():
    result = build_extract_invoice(model())(pdf_of(TWO_COLUMN_TEXT))

    assert result.status is JobStatus.SUCCEEDED, result.errors
    assert result.extraction.seller.name == "TechVision Distributors Pvt Ltd"
    assert result.extraction.client.name == "Raj Electronics Pvt Ltd"
    assert result.extraction.seller.tax_id == "27AABCT1234F1Z5"
    assert result.extraction.client.tax_id == "901-95-4704"
    assert result.extraction.client.address == "42 MG Road, Bengaluru, Karnataka - 560001"


def test_result_does_not_expose_the_placeholder_map():
    result = build_extract_invoice(model())(pdf_of(TWO_COLUMN_TEXT))

    assert not hasattr(result, "placeholders")


def test_leftover_placeholder_is_rejected():
    result = build_extract_invoice(model(**{"seller.name": "[NAME_9]"}))(pdf_of(TWO_COLUMN_TEXT))

    assert result.status is JobStatus.FAILED_VALIDATION
    assert result.reason is TerminalReason.OUTPUT_REJECTED
    assert result.extraction is None


def test_altered_placeholder_is_rejected():
    result = build_extract_invoice(model(**{"seller.tax_id": "TAX_ID_1"}))(pdf_of(TWO_COLUMN_TEXT))

    assert result.reason is TerminalReason.OUTPUT_REJECTED


def test_placeholder_in_a_field_of_another_kind_is_rejected():
    result = build_extract_invoice(model(**{"seller.name": "[TAX_ID_1]"}))(pdf_of(TWO_COLUMN_TEXT))

    assert result.reason is TerminalReason.OUTPUT_REJECTED


def test_sensitive_value_leaking_into_a_free_field_is_rejected():
    result = build_extract_invoice(model(invoice_no="[TAX_ID_1]"))(pdf_of(TWO_COLUMN_TEXT))

    assert result.reason is TerminalReason.OUTPUT_REJECTED


def test_malformed_values_are_rejected():
    result = build_extract_invoice(model(**{"client.name": "x" * 1000}))(pdf_of(TWO_COLUMN_TEXT))

    assert result.reason is TerminalReason.OUTPUT_REJECTED
