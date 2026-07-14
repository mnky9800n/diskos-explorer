"""Corpus-level index across all wells: coverage, quadrant grouping, finding.

This is the start of the "larger context" layer (deliverable #1): instead of
looking at one well, answer questions over the whole archive, "which wells have
biostrat reports", "how well is quadrant 35 logged", and compare wells.

Building the index scans every well, but cheaply: it reads each well's immediate
category subdirs (one scandir per well) rather than recursing all 84k files, and
peeks into GEOLOGY only to flag biostrat. It is cached per data-root for the
process lifetime (first call is a few seconds over the mounted tree; the rest are
instant).
"""

from __future__ import annotations

import re
from pathlib import Path

from .. import wells as wells_mod

_WELL_ID_RE = re.compile(r"^(\d+)_(\d+)-")

# category-subdir name (upper) -> data type
_CATEGORY_TYPE = {
    "LOGS": "logs", "WELL_LOG": "logs", "PETROPHYSICS": "logs",
    "WELL_SEISMIC": "seismic",
    "WELL_PATH": "deviation",
    "GEOLOGY": "geology", "REPORTS": "geology", "WELL_STRAT": "geology",
    "DRILLING": "drilling",
    "ROCK_AND_CORE": "core",
}

_CACHE: dict[str, list[dict]] = {}


def parse_quadrant_block(well_id: str) -> tuple[str | None, str | None]:
    """Norwegian well ID -> (quadrant, block). Named wells (ADDA-1) return (None, None)."""
    m = _WELL_ID_RE.match(well_id)
    return (m.group(1), m.group(2)) if m else (None, None)


def _well_entry(well_dir: Path) -> dict:
    types: set[str] = set()
    biostrat = False
    core = False
    try:
        subdirs = [d for d in well_dir.iterdir() if d.is_dir()]
    except OSError:
        subdirs = []
    for d in subdirs:
        t = _CATEGORY_TYPE.get(d.name.upper())
        if t:
            types.add(t)
        if d.name.upper() == "GEOLOGY":
            try:
                biostrat = any("BIOSTRAT" in f.name.upper() for f in d.iterdir())
            except OSError:
                pass
        if d.name.upper() == "ROCK_AND_CORE":
            core = True
    q, b = parse_quadrant_block(well_dir.name)
    return {
        "well_id": well_dir.name,
        "quadrant": q,
        "block": b,
        "types": sorted(types),
        "biostrat": biostrat,
        "core": core,
    }


def build_index(root: Path, refresh: bool = False) -> list[dict]:
    """Build (or return cached) the per-well coverage index."""
    key = str(root)
    if refresh or key not in _CACHE:
        _CACHE[key] = [_well_entry(root / wid) for wid in wells_mod.list_well_ids(root)]
    return _CACHE[key]


def stats(index: list[dict]) -> dict:
    """Aggregate coverage across the corpus."""
    coverage: dict[str, int] = {}
    for entry in index:
        for t in entry["types"]:
            coverage[t] = coverage.get(t, 0) + 1
    by_quadrant: dict[str, int] = {}
    for entry in index:
        q = entry["quadrant"] or "named"
        by_quadrant[q] = by_quadrant.get(q, 0) + 1
    return {
        "n_wells": len(index),
        "coverage": dict(sorted(coverage.items(), key=lambda kv: -kv[1])),
        "biostrat": sum(1 for e in index if e["biostrat"]),
        "core": sum(1 for e in index if e["core"]),
        "by_quadrant": dict(sorted(by_quadrant.items(), key=lambda kv: -kv[1])),
    }


def find(index: list[dict], data_type: str | None = None, biostrat: bool | None = None,
         core: bool | None = None, quadrant: str | None = None, limit: int = 200) -> list[dict]:
    """Filter wells by coverage / quadrant."""
    out = []
    for entry in index:
        if data_type and data_type not in entry["types"]:
            continue
        if biostrat and not entry["biostrat"]:
            continue
        if core and not entry["core"]:
            continue
        if quadrant and entry["quadrant"] != quadrant:
            continue
        out.append(entry)
    return out[:limit]
