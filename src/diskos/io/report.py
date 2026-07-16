"""Read text out of report PDFs. Pure IO: pypdf only, no analysis, no model.

One shared reader so the wiki dossier, the provenance graph, and the web
assistant do not each carry their own pypdf snippet. Many DISKOS reports are
scanned images with no text layer; those return an empty string, which callers
treat as "no extractable text" rather than an error.
"""

from __future__ import annotations

import re
from pathlib import Path

# "2037.5m - 2274.8m", "2037.5 - 2274.8 m", "2037-2275m"
_INTERVAL_RE = re.compile(r"(\d{3,4}(?:\.\d+)?)\s*m?\s*[-–]\s*(\d{3,4}(?:\.\d+)?)\s*m", re.I)
_MAX_DEPTH = 7000.0


def depth_interval(text: str, max_depth: float = _MAX_DEPTH) -> list[float] | None:
    """Widest plausible depth interval [top, bottom] mentioned in report text."""
    tops, bots = [], []
    for top, bottom in _INTERVAL_RE.findall(text):
        top, bottom = float(top), float(bottom)
        if top < bottom <= max_depth:
            tops.append(top)
            bots.append(bottom)
    if not tops:
        return None
    return [min(tops), max(bots)]


def read_pdf_text(
    path: str | Path,
    max_pages: int | None = None,
    max_chars: int | None = None,
    max_bytes: int | None = 60 * 1024 * 1024,
) -> str:
    """Extract text from a PDF. Returns "" on failure or a scanned (imageless) PDF.

    ``max_pages`` limits how many pages are read (cheap first-pages skim);
    ``max_chars`` truncates the result. ``max_bytes`` skips very large files
    (essentially always image-only scans in this archive) so a whole-archive
    sweep does not stall parsing hundred-megabyte reports with no text layer.
    """
    from pypdf import PdfReader

    try:
        if max_bytes is not None and Path(path).stat().st_size > max_bytes:
            return ""
        reader = PdfReader(str(path))
        pages = reader.pages if max_pages is None else reader.pages[:max_pages]
        text = "".join((page.extract_text() or "") for page in pages)
    except Exception:
        return ""
    text = text.strip()
    if max_chars is not None:
        text = text[:max_chars]
    return text
