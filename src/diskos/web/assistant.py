"""Well assistant: answer questions about a well using the local model.

Grounds the local model (Ollama on lambda-scalar by default) in the well's own
report text. Biostratigraphy / geology PDFs are the richest source (species,
ages, zonations), so their extractable text becomes the context. Some older
reports are pure scans with no text layer; those are noted, OCR is a later add.

The model endpoint is env-configured so the same code points at lambda-scalar
Ollama in production or any OpenAI-compatible endpoint elsewhere.
"""

from __future__ import annotations

import os
from pathlib import Path

from ..llm.client import LLMClient
from ..llm.profiles import system_prompt_for

MAX_REPORT_CHARS = 8000


def make_client() -> LLMClient:
    """Build the assistant's model client from the environment.

    Defaults target Ollama on the same host (the app runs next to it on
    lambda-scalar). Override with OLLAMA_BASE_URL / DISKOS_ASSISTANT_MODEL.
    """
    return LLMClient(
        base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        model=os.environ.get("DISKOS_ASSISTANT_MODEL", "qwen2.5:32b"),
        api_key=os.environ.get("OLLAMA_API_KEY", "ollama"),
        system=system_prompt_for("jack-serve"),
    )


def _biostrat_first(paths: list[Path]) -> list[Path]:
    return sorted(paths, key=lambda p: (0 if "biostrat" in p.name.lower() else 1, p.name))


def extract_report_text(paths: list[Path], max_chars: int = MAX_REPORT_CHARS) -> tuple[str, list[str]]:
    """Extract text from report PDFs (biostrat first). Returns (text, used_files).

    Files with no text layer (scans) are noted but do not consume the budget.
    """
    from pypdf import PdfReader

    chunks: list[str] = []
    used: list[str] = []
    total = 0
    for path in _biostrat_first(paths):
        if total >= max_chars:
            break
        try:
            reader = PdfReader(str(path))
            text = "".join((pg.extract_text() or "") for pg in reader.pages).strip()
        except Exception:
            text = ""
        if text:
            snippet = text[: max_chars - total]
            chunks.append(f"--- {path.name} ---\n{snippet}")
            used.append(path.name)
            total += len(snippet)
        else:
            chunks.append(f"--- {path.name} ---\n(scanned image, no extractable text)")
    return "\n\n".join(chunks), used


def format_inventory(well) -> str:
    """A human-readable list of what data/files the well has, by type."""
    lines = []
    for data_type, paths in well.files.items():
        shown = [p.name for p in paths[:6]]
        more = f", +{len(paths) - 6} more" if len(paths) > 6 else ""
        lines.append(f"- {data_type} ({len(paths)}): {', '.join(shown)}{more}")
    return "\n".join(lines) or "(no catalogued files)"


def build_prompt(well_id: str, inventory: str, report_text: str, question: str) -> str:
    reports = report_text or "(no geology/biostratigraphy report text is available for this well)"
    return (
        f"You are assisting a geologist with Norwegian DISKOS well {well_id}. "
        f"Two kinds of context follow.\n\n"
        f"DATA INVENTORY (the files this well has):\n{inventory}\n\n"
        f"REPORT EXCERPTS (geology / biostratigraphy text, if any):\n{reports}\n\n"
        f"Answer the question. Use the DATA INVENTORY to describe what data or files "
        f"the well holds. Use the REPORT EXCERPTS for geological interpretation (ages, "
        f"zones, species, depths), citing the report file name. If the excerpts do not "
        f"cover something asked, say the reports do not include it. Do not invent "
        f"findings. Be concise.\n\n"
        f"QUESTION: {question}"
    )


def answer_question(well, question: str, client: LLMClient | None = None) -> dict:
    """Answer a question about a well, grounded in its inventory + report PDFs."""
    client = client or make_client()
    report_paths = well.files.get("geology", [])
    report_text, used = extract_report_text(report_paths)
    prompt = build_prompt(well.well_id, format_inventory(well), report_text, question)
    reply = client.ask(prompt, max_tokens=600, temperature=0.2)
    return {"answer": reply, "sources": used, "reports_available": [p.name for p in report_paths]}
