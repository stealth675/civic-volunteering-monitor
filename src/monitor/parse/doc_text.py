from __future__ import annotations


def extract_docx_text(content: bytes) -> str:
    try:
        from docx import Document
    except Exception:
        return ""
    from io import BytesIO

    doc = Document(BytesIO(content))
    return "\n".join(p.text for p in doc.paragraphs).strip()
