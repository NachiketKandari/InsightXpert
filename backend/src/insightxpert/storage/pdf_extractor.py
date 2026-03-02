"""PDF text extraction utility."""
from __future__ import annotations
import io
import logging

logger = logging.getLogger("insightxpert.storage")


def extract_text_from_pdf(content: bytes) -> tuple[str, int]:
    """Extract text from a PDF file.

    Returns (extracted_text, page_count).
    Adds page markers between pages.
    """
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    page_count = len(reader.pages)

    if page_count == 0:
        return "", 0

    pages: list[str] = []
    for i, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        text = text.strip()
        if text:
            pages.append(f"--- Page {i} ---\n{text}")
        else:
            pages.append(f"--- Page {i} ---\n[No extractable text on this page]")

    full_text = "\n\n".join(pages)

    # Check if essentially empty (scanned PDF with no OCR)
    non_marker_text = full_text.replace("--- Page", "").replace("---", "").replace("[No extractable text on this page]", "").strip()
    if not non_marker_text:
        full_text = f"[Scanned PDF with {page_count} pages — no extractable text. OCR may be needed.]"

    return full_text, page_count
