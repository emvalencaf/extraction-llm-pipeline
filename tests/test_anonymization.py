"""Seam 2: the Presidio detector behind the SensitiveDetector port, measured as Leak Rate."""

import pytest

from invoice_extraction.adapters.presidio_detector import PresidioDetector
from invoice_extraction.application.privacy import anonymize
from support.invoices import (
    CONTACT_TEXT,
    CONTACT_VALUES,
    SENSITIVE_VALUES,
    TWO_COLUMN_TEXT,
    leak_rate,
)


@pytest.fixture(scope="module")
def detector():
    return PresidioDetector()


def anonymized(detector, text):
    return anonymize(text, detector.detect(text))


def test_leak_rate_is_zero_on_the_dataset_template(detector):
    text, _ = anonymized(detector, TWO_COLUMN_TEXT)

    assert leak_rate([(text, SENSITIVE_VALUES)]) == 0.0


def test_leak_rate_is_zero_on_contact_and_bank_details(detector):
    text, _ = anonymized(detector, CONTACT_TEXT)

    assert leak_rate([(text, CONTACT_VALUES)]) == 0.0


def test_amounts_dates_invoice_number_and_descriptions_are_kept(detector):
    text, _ = anonymized(detector, TWO_COLUMN_TEXT)

    for kept in ("51109301", "03/07/2023", "Garmin Fenix 7 Solar", "1,844,673.60", "INR"):
        assert kept in text


def test_same_value_shares_one_placeholder(detector):
    text, _ = anonymized(detector, TWO_COLUMN_TEXT)

    assert text.count("[TAX_ID_1]") == 2  # seller Tax Id and GSTIN are the same value
    assert "[TAX_ID_2]" in text  # the client's differs
    assert "[NAME_1]" in text
    assert "[NAME_2]" in text


def test_indian_identifiers_are_detected_in_any_context(detector):
    text, _ = anonymized(detector, "Ref 27AABCT1234F1Z5 / PAN AABCT1234F / 901-95-4704.")

    assert "27AABCT1234F1Z5" not in text
    assert "AABCT1234F" not in text
    assert "901-95-4704" not in text
