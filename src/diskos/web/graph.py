"""Per-well provenance graph: how each report attaches to the well's data files.

The raw archive has no explicit links, so connections are inferred (deterministic,
no LLM for this first version):

  - A report states a studied depth interval in its text ("2037.5m - 2274.8m").
    A LAS log covers a depth range. If they overlap, the report attaches to that
    log (edge reason: depth overlap).
  - If a report's text mentions core / sidewall / cuttings and the well has core,
    the report attaches to those core files.

Reports we cannot read (scanned, no text) or cannot place (no interval found)
appear as unconnected nodes, which is honest, it shows what could not be linked.
Richer LLM-based extraction is the planned upgrade.
"""

from __future__ import annotations

import re

from .. import wells as wells_mod
from ..io.report import depth_interval as report_interval

_SAMPLE_RE = re.compile(r"\b(core|sidewall|swc|cutting)", re.I)
_MAX_REPORT_PAGES = 6


def _overlaps(a: list[float], b: list[float]) -> bool:
    return not (a[1] < b[0] or b[1] < a[0])


def _read_report_text(path) -> str:
    from ..io.report import read_pdf_text

    return read_pdf_text(path, max_pages=_MAX_REPORT_PAGES)


def _log_range(path) -> list[float] | None:
    from ..welllog import curves as wl

    try:
        df = wl.read_las(path)
        idx = df.index.to_numpy(dtype=float)
        return [float(idx.min()), float(idx.max())]
    except Exception:
        return None


def build_well_graph(well, max_logs: int = 12, max_core: int = 12) -> dict:
    """Build the report/data graph for a well: nodes + inferred edges."""
    nodes: list[dict] = []
    edges: list[dict] = []

    reports = []
    for p in well.files.get("geology", []):
        if p.suffix.lower() != ".pdf":
            continue
        text = _read_report_text(p)
        interval = report_interval(text)
        rid = f"report:{p.name}"
        nodes.append({
            "id": rid, "label": p.name, "kind": "report",
            "biostrat": wells_mod.is_biostrat(p), "interval": interval,
        })
        reports.append((rid, interval, bool(_SAMPLE_RE.search(text))))

    logs = []
    for p in well.files.get("logs", [])[:max_logs]:
        rng = _log_range(p)
        lid = f"log:{p.name}"
        nodes.append({"id": lid, "label": p.name, "kind": "log", "range": rng})
        logs.append((lid, rng))

    cores = []
    for p in well.files.get("core", [])[:max_core]:
        cid = f"core:{p.name}"
        nodes.append({"id": cid, "label": p.name, "kind": "core"})
        cores.append(cid)

    for rid, interval, mentions_core in reports:
        for lid, rng in logs:
            if interval and rng and _overlaps(interval, rng):
                edges.append({"source": rid, "target": lid, "reason": f"depth overlap {interval[0]:.0f}-{interval[1]:.0f} m"})
        if mentions_core and cores:
            for cid in cores:
                edges.append({"source": rid, "target": cid, "reason": "report mentions core/cuttings"})

    return {"well_id": well.well_id, "nodes": nodes, "edges": edges}
