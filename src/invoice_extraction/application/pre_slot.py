"""Pre slot: everything done to a PDF before the model call.

Each step is its own small function so the graph can wire them as separate nodes:
`check_pdf` (limits), `read_text` + `clean_text` (cleanup), `anonymize_text` (privacy).
"""

import re
import unicodedata
from dataclasses import dataclass

from invoice_extraction.application.ports import (
    PdfPageCounter,
    PdfTextReader,
    PdfUnreadableError,
    SensitiveDetector,
)
from invoice_extraction.application.privacy import PlaceholderMap, anonymize
from invoice_extraction.domain.status import MAX_PDF_BYTES, MAX_PDF_PAGES, TerminalReason


class RejectedError(Exception):
    """The job ends here with a terminal reason."""

    def __init__(self, reason: TerminalReason, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class Prepared:
    """What the model call receives, plus the in-memory map needed to Restore."""

    text: str
    placeholders: PlaceholderMap


def check_pdf(pdf: bytes, pages: PdfPageCounter) -> None:
    if len(pdf) > MAX_PDF_BYTES:
        raise RejectedError(TerminalReason.PDF_TOO_LARGE, f"PDF exceeds {MAX_PDF_BYTES} bytes")
    try:
        count = pages.page_count(pdf)
    except PdfUnreadableError as error:
        raise RejectedError(TerminalReason.PDF_UNREADABLE, str(error)) from error
    if count > MAX_PDF_PAGES:
        raise RejectedError(
            TerminalReason.PDF_TOO_LONG, f"PDF has {count} pages, max {MAX_PDF_PAGES}"
        )


def read_text(pdf: bytes, reader: PdfTextReader) -> str:
    try:
        return reader.read(pdf)
    except PdfUnreadableError as error:
        raise RejectedError(TerminalReason.PDF_UNREADABLE, str(error)) from error


def clean_text(text: str) -> str:
    """NFC, drop control characters, collapse blanks; keep line structure."""
    text = unicodedata.normalize("NFC", text)
    text = "".join(c for c in text if c in "\n\t" or unicodedata.category(c)[0] != "C")
    lines = (re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def anonymize_text(text: str, detector: SensitiveDetector) -> Prepared:
    anonymized, placeholders = anonymize(text, detector.detect(text))
    return Prepared(anonymized, placeholders)


class PreSlot:
    def __init__(
        self,
        reader: PdfTextReader,
        pages: PdfPageCounter,
        detector: SensitiveDetector,
    ) -> None:
        self._reader = reader
        self._pages = pages
        self._detector = detector

    def __call__(self, pdf: bytes) -> Prepared:
        check_pdf(pdf, self._pages)
        text = clean_text(read_text(pdf, self._reader))
        return anonymize_text(text, self._detector)
