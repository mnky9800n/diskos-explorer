"""Read text out of report PDFs. Pure IO: pypdf only, no analysis, no model.

One shared reader so the wiki dossier, the provenance graph, and the web
assistant do not each carry their own pypdf snippet. Many DISKOS reports are
scanned images with no text layer; those return an empty string, which callers
treat as "no extractable text" rather than an error.
"""

from __future__ import annotations

from pathlib import Path


def read_pdf_text(
    path: str | Path,
    max_pages: int | None = None,
    max_chars: int | None = None,
) -> str:
    """Extract text from a PDF. Returns "" on failure or a scanned (imageless) PDF.

    ``max_pages`` limits how many pages are read (cheap first-pages skim);
    ``max_chars`` truncates the result.
    """
    from pypdf import PdfReader

    try:
        reader = PdfReader(str(path))
        pages = reader.pages if max_pages is None else reader.pages[:max_pages]
        text = "".join((page.extract_text() or "") for page in pages)
    except Exception:
        return ""
    text = text.strip()
    if max_chars is not None:
        text = text[:max_chars]
    return text
