"""PdfTextReader backed by pypdf (text-native PDFs only)."""

from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from invoice_extraction.application.ports import PdfUnreadableError


class PypdfTextReader:
    def read(self, pdf: bytes) -> str:
        try:
            reader = PdfReader(BytesIO(pdf))
            return "\n".join(page.extract_text() for page in reader.pages)
        except (PyPdfError, ValueError, OSError) as error:
            raise PdfUnreadableError(f"cannot read PDF: {error}") from error
