from __future__ import annotations

from io import BytesIO
from pypdf import PdfReader


def extract_pdf_text(content: bytes) -> tuple[str, bool]:
    reader = PdfReader(BytesIO(content))
    pages = []
    for p in reader.pages:
        pages.append(p.extract_text() or "")
    text = "\n".join(pages).strip()
    needs_ocr = len(text) < 200
    return text, needs_ocr
