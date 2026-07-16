"""OCR scanned report PDFs with a local vision model, cached to disk.

Most DISKOS biostratigraphy reports are image-only scans with no text layer, so
`read_pdf_text` returns nothing for them, and those are exactly the reports with
the species lists and biozone charts the wiki most wants. This module rasterizes
a scan's pages (PyMuPDF) and reads each with the local vision model (qwen2.5vl via
the `vision` profile), caching the transcript next to the archive (never in it).

OCR is expensive, so it is a separate, resumable enrichment pass: run it once,
then `diskos wiki build` picks the cached text up through `cached_ocr` and only
the pages that gained report text regenerate.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .report import read_pdf_text

_OCR_PROMPT = (
    "This is a scanned page from a petroleum well biostratigraphy or geology report. "
    "Transcribe every readable text element verbatim: headers, paragraphs, and "
    "especially any tables of species names with their depths, ages, or biozones. "
    "Keep all numbers exact. Output only the transcribed text. If the page has no "
    "readable text, output the single word NONE."
)


def ocr_cache_path(pdf_path: str | Path, ocr_dir: str | Path) -> Path:
    """Stable cache file for a PDF's OCR transcript (hash-prefixed to avoid clashes)."""
    pdf_path = Path(pdf_path)
    digest = hashlib.sha1(str(pdf_path.resolve()).encode("utf-8")).hexdigest()[:10]
    return Path(ocr_dir) / f"{digest}_{pdf_path.stem}.txt"


def cached_ocr(pdf_path: str | Path, ocr_dir: str | Path | None) -> str | None:
    """Return a PDF's cached OCR transcript if present, else None."""
    if ocr_dir is None:
        return None
    path = ocr_cache_path(pdf_path, ocr_dir)
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8").strip()
    return text or None


def has_text_layer(pdf_path: str | Path) -> bool:
    """Whether a PDF already yields extractable text (so it needs no OCR)."""
    return bool(read_pdf_text(pdf_path, max_pages=6))


def ocr_pdf(
    pdf_path: str | Path,
    client,
    ocr_dir: str | Path,
    max_pages: int = 12,
    dpi: int = 150,
    force: bool = False,
) -> str:
    """OCR one scanned PDF page-by-page with the vision model, cache and return text.

    Returns the cached transcript if present (unless ``force``). Renders up to
    ``max_pages`` pages; pages the model reads as blank are dropped.
    """
    ocr_dir = Path(ocr_dir)
    cache = ocr_cache_path(pdf_path, ocr_dir)
    if cache.is_file() and not force:
        return cache.read_text(encoding="utf-8")

    import fitz  # PyMuPDF

    tmp_dir = ocr_dir / ".pages"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    parts: list[str] = []
    try:
        doc = fitz.open(str(pdf_path))
    except Exception:
        return ""
    for i, page in enumerate(doc):
        if i >= max_pages:
            break
        tmp_png = tmp_dir / f"p{i}.png"
        try:
            page.get_pixmap(dpi=dpi).save(str(tmp_png))
            text = client.chat_vision(_OCR_PROMPT, [tmp_png], temperature=0.0).strip()
        except Exception:
            text = ""
        finally:
            tmp_png.unlink(missing_ok=True)
        if text and text.upper() != "NONE":
            parts.append(f"[page {i + 1}]\n{text}")
    doc.close()

    transcript = "\n\n".join(parts)
    ocr_dir.mkdir(parents=True, exist_ok=True)
    cache.write_text(transcript, encoding="utf-8")
    return transcript


def ocr_reports(
    paths: list[Path],
    client,
    ocr_dir: str | Path,
    max_pages: int = 12,
    force: bool = False,
    on_each=None,
) -> list[dict]:
    """OCR a batch of report PDFs, skipping ones with a text layer or already cached.

    Returns a per-file status list. ``on_each(status)`` is called after each file
    for progress reporting.
    """
    results: list[dict] = []
    for path in paths:
        status = {"file": Path(path).name, "state": "", "chars": 0}
        if not force and cached_ocr(path, ocr_dir) is not None:
            status["state"] = "cached"
        elif has_text_layer(path):
            status["state"] = "has-text"
        else:
            text = ocr_pdf(path, client, ocr_dir, max_pages=max_pages, force=force)
            status["state"] = "ocr" if text else "empty"
            status["chars"] = len(text)
        results.append(status)
        if on_each:
            on_each(status)
    return results
