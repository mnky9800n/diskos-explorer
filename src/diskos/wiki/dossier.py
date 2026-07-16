"""Compile one borehole's structured facts: the input to a wiki page.

A dossier is the deterministic, model-free summary of everything the archive
knows about a physical borehole (a `BoreholeGroup`): identity and sidetracks,
resolved location and field, a deduped file inventory, log curves and depth
ranges, report presence and studied intervals, any palynology summary, and its
nearest neighbours. The wiki page is rendered from this dict, and the LLM is
handed this dict to synthesize prose, so extraction happens once and a better
model can be re-run later over the same dossiers.

House rule: state gaps plainly. Absence here means "not in the mirror," never
"does not exist."
"""

from __future__ import annotations

import math
from pathlib import Path

from .. import wells as wells_mod
from ..boreholes import BoreholeGroup

_MAX_LOGS = 4
_MAX_REPORTS = 6
_REPORT_EXCERPT_CHARS = 1800
_MAX_NEIGHBORS = 5


def _log_facts(group: BoreholeGroup) -> list[dict]:
    from ..welllog import curves as wl

    facts: list[dict] = []
    for las in group.files.get("logs", [])[:_MAX_LOGS]:
        try:
            df = wl.read_las(las)
        except Exception:
            continue
        depth = df.index.to_numpy(dtype=float)
        entry: dict = {
            "file": las.name,
            "mnemonics": wl.available_mnemonics(df),
            "depth": [float(depth.min()), float(depth.max())] if depth.size else None,
        }
        try:
            gamma = wl.gamma_column(df)
            series = df[gamma].dropna()
            entry["gamma"] = {
                "curve": gamma,
                "min": float(series.min()),
                "mean": float(series.mean()),
                "max": float(series.max()),
            }
        except Exception:
            pass
        facts.append(entry)
    return facts


def _report_facts(group: BoreholeGroup) -> tuple[list[dict], str]:
    from ..io.report import depth_interval, read_pdf_text

    reports = [p for p in group.files.get("geology", []) if p.suffix.lower() == ".pdf"]
    reports.sort(key=lambda p: (0 if wells_mod.is_biostrat(p) else 1, p.name))

    facts: list[dict] = []
    excerpt_parts: list[str] = []
    budget = _REPORT_EXCERPT_CHARS
    for path in reports[:_MAX_REPORTS]:
        text = read_pdf_text(path, max_pages=8)
        facts.append({
            "file": path.name,
            "biostrat": wells_mod.is_biostrat(path),
            "has_text": bool(text),
            "interval": depth_interval(text) if text else None,
        })
        if text and budget > 0:
            take = text[:budget]
            excerpt_parts.append(f"--- {path.name} ---\n{take}")
            budget -= len(take)
    return facts, "\n\n".join(excerpt_parts)


def _palyno_facts(group: BoreholeGroup, out_dir: Path | None) -> dict | None:
    if out_dir is None or not Path(out_dir).is_dir():
        return None
    from ..palyno.plot import palyno_well_key_from_fname
    from .ingest import summarize_well_csv

    keys = set(group.well_ids) | {group.borehole_id}
    for csv_path in sorted(Path(out_dir).glob("*.csv")):
        try:
            key = palyno_well_key_from_fname(csv_path.name)
        except Exception:
            continue
        if key in keys:
            summary = summarize_well_csv(csv_path)
            summary["source"] = csv_path.name
            return summary
    return None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def _neighbors(group: BoreholeGroup, all_groups: dict[str, BoreholeGroup] | None) -> list[dict]:
    if not all_groups or group.lat is None or group.lon is None:
        return []
    scored = []
    for other in all_groups.values():
        if other.borehole_id == group.borehole_id or other.lat is None or other.lon is None:
            continue
        km = _haversine_km(group.lat, group.lon, other.lat, other.lon)
        scored.append((km, other))
    scored.sort(key=lambda t: t[0])
    return [
        {"borehole_id": o.borehole_id, "field": o.field_name, "distance_km": round(km, 1)}
        for km, o in scored[:_MAX_NEIGHBORS]
    ]


def build_dossier(
    group: BoreholeGroup,
    all_groups: dict[str, BoreholeGroup] | None = None,
    out_dir: Path | None = None,
) -> dict:
    """Assemble the structured facts for one borehole. Model-free and deterministic."""
    reports, report_excerpt = _report_facts(group)
    npd = group.npd
    return {
        "borehole_id": group.borehole_id,
        "well_ids": group.well_ids,
        "sidetracks": group.sidetracks,
        "location": {
            "lat": group.lat,
            "lon": group.lon,
            "field": group.field_name,
            "block": group.block,
            "quadrant": group.quadrant,
            "coord_source": group.coord_source,
            "npdid": group.npdid,
        },
        "npd": (
            {
                "operator": npd.operator,
                "purpose": npd.purpose,
                "content": npd.content,
                "well_type": npd.well_type,
            }
            if npd is not None
            else None
        ),
        "inventory": {t: group.count(t) for t in wells_mod.DATA_TYPES if group.count(t)},
        "inventory_files": {
            t: [p.name for p in group.files.get(t, [])[:8]]
            for t in wells_mod.DATA_TYPES
            if group.count(t)
        },
        "duplicate_count": len(group.duplicate_pairs),
        "logs": _log_facts(group),
        "reports": reports,
        "report_excerpt": report_excerpt,
        "palynology": _palyno_facts(group, out_dir),
        "neighbors": _neighbors(group, all_groups),
    }
