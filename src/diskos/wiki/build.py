"""Build the wiki over the DISKOS archive: borehole pages, then field pages.

Two passes, each grounded in a deterministic dossier:

  1. one page per physical borehole (identity, location, data, gaps), authored by
     the fast local model (or deterministically with no model);
  2. one page per area (NPD field when known, else block), synthesizing the
     boreholes that belong together, authored by the stronger local model.

Scope is one field/block, one well, or the whole archive. The per-borehole pass
is resumable: an unchanged borehole (same dossier hash) is skipped.
"""

from __future__ import annotations

import re
from datetime import date as _date
from pathlib import Path

from .. import npd as npd_mod
from .. import wells as wells_mod
from ..boreholes import borehole_id, group_boreholes, quadrant_block
from .dossier import build_dossier
from .ingest import ingest_borehole, ingest_field

_BLOCK_RE = re.compile(r"^\d+_\d+$")


def _scope_well_ids(root: Path, scope: tuple[str, str] | str, records: dict) -> list[str]:
    all_ids = wells_mod.list_well_ids(root)
    if scope == "all" or scope is None:
        return all_ids
    kind, value = scope
    if kind == "well":
        target = borehole_id(value, records)
        return [wid for wid in all_ids if borehole_id(wid, records) == target]
    if kind == "field":
        if _BLOCK_RE.match(value):  # a block like 31_2
            return [wid for wid in all_ids if quadrant_block(wid)[1] == value]
        # else an NPD field name: match on the register
        want = value.upper()
        out = []
        for wid in all_ids:
            record = npd_mod.match(records, wid)
            if record and record.field and record.field.upper() == want:
                out.append(wid)
        return out
    raise ValueError(f"unknown scope {scope!r}")


def _area(dossier: dict) -> tuple[str, str]:
    """(key, display) for the area page a borehole belongs to."""
    loc = dossier["location"]
    if loc.get("field"):
        return loc["field"], f"{loc['field']} field"
    if loc.get("block"):
        return loc["block"], f"Block {loc['block']}"
    return "unlocated", "Unlocated boreholes"


def build_wiki(
    root: str | Path,
    wiki_dir: str | Path,
    scope: tuple[str, str] | str = "all",
    well_client=None,
    field_client=None,
    out_dir: str | Path | None = None,
    npd_dir: str | Path | None = None,
    force: bool = False,
    on_date: str | None = None,
) -> dict:
    """Run the wiki build over a scope. Returns a summary of what was written."""
    root = Path(root)
    wiki_dir = Path(wiki_dir)
    on_date = on_date or _date.today().isoformat()
    records = npd_mod.load_factpages(npd_dir) if npd_dir else {}

    well_ids = _scope_well_ids(root, scope, records)
    catalog = {wid: wells_mod.well_files(root, wid) for wid in well_ids}
    groups = group_boreholes(catalog, records)

    # Pass 1: per-borehole pages.
    dossiers: list[dict] = []
    written = skipped = 0
    for group in groups.values():
        dossier = build_dossier(group, all_groups=groups, out_dir=out_dir)
        dossiers.append(dossier)
        path = ingest_borehole(dossier, wiki_dir, on_date, client=well_client, force=force)
        if path is None:
            skipped += 1
        else:
            written += 1

    # Pass 2: per-area pages.
    areas: dict[str, tuple[str, list[dict]]] = {}
    for dossier in dossiers:
        key, display = _area(dossier)
        areas.setdefault(key, (display, []))[1].append(dossier)
    for key, (display, members) in areas.items():
        ingest_field(key, display, members, wiki_dir, on_date, client=field_client)

    return {
        "boreholes": len(groups),
        "pages_written": written,
        "pages_skipped": skipped,
        "areas": len(areas),
        "directories": len(well_ids),
    }
