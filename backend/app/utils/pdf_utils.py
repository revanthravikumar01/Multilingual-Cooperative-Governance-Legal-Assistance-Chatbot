"""Read PDFs: validate them and pull out text page by page.

Uses pypdf, a pure-Python library (no native files, so Windows Smart App Control
does not block it). It keeps page order, which we need for page-number citations.
"""

import io
import logging
import re
from dataclasses import dataclass

from pypdf import PdfReader
from pypdf.errors import PdfReadError

# pypdf logs a warning for every small formatting quirk in government PDFs; keep the console readable.
logging.getLogger("pypdf").setLevel(logging.ERROR)

# Tamil Unicode block. Used to spot Tamil PDFs whose text comes out as garbage.
_TAMIL_CHARS = re.compile(r"[஀-௿]")
_LETTERS = re.compile(r"[^\W\d_]|[஀-௿]")

# A page with fewer readable characters than this is probably a scanned image.
MIN_CHARS_PER_PAGE = 40


class PdfError(ValueError):
    """The file is not a usable PDF. The message is safe to show to the uploader."""


@dataclass
class PageText:
    page_number: int  # 1-based, as printed in a PDF viewer
    text: str


def _open(source) -> PdfReader:
    reader = PdfReader(source)
    if reader.is_encrypted:
        # Many government PDFs are "encrypted" only to block editing; an empty password opens them.
        if not reader.decrypt(""):
            raise PdfError("The PDF is password-protected.")
    return reader


def validate_pdf(data: bytes, max_bytes: int) -> int:
    """Check the bytes are a readable, unlocked PDF. Returns the page count."""
    if not data:
        raise PdfError("The file is empty.")
    if len(data) > max_bytes:
        raise PdfError(f"The file is larger than {max_bytes // (1024 * 1024)} MB.")
    if not data.lstrip()[:5] == b"%PDF-":
        raise PdfError("The file is not a PDF.")
    try:
        reader = _open(io.BytesIO(data))
        page_count = len(reader.pages)
    except PdfError:
        raise
    except (PdfReadError, Exception) as exc:  # broken files raise many different errors
        raise PdfError(f"The PDF could not be opened: {exc}") from exc
    if page_count == 0:
        raise PdfError("The PDF has no pages.")
    return page_count


def extract_pages(path: str) -> list[PageText]:
    """Return the text of every page, keeping page numbers for citations."""
    reader = _open(path)
    pages: list[PageText] = []
    for index, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except Exception:  # one damaged page should not fail the whole document
            text = ""
        pages.append(PageText(page_number=index + 1, text=text))
    return pages


def text_quality_warnings(pages: list[PageText], language: str) -> list[str]:
    """Spot PDFs whose text cannot be trusted (scanned images, old Tamil fonts)."""
    warnings: list[str] = []
    if not pages:
        return ["No pages were read."]

    empty_pages = [p.page_number for p in pages if len(p.text.strip()) < MIN_CHARS_PER_PAGE]
    if len(empty_pages) == len(pages):
        warnings.append("No readable text found. This looks like a scanned PDF and needs OCR.")
    elif len(empty_pages) > len(pages) / 2:
        warnings.append(f"{len(empty_pages)} of {len(pages)} pages have almost no text (possibly scanned).")

    if language == "ta":
        all_text = "".join(p.text for p in pages)
        letters = _LETTERS.findall(all_text)
        tamil = _TAMIL_CHARS.findall(all_text)
        if letters and len(tamil) / len(letters) < 0.3:
            warnings.append(
                "Marked as Tamil, but very little Tamil Unicode text was found. The PDF may use an "
                "old non-Unicode Tamil font, so the extracted text may be unreadable."
            )
    return warnings
