"""Resolve DISKOS directories into physical boreholes, located and grouped.

`wells.py` treats every top-level directory as an independent well keyed by its
raw name. But the ~3045 directories are really ~2362 physical boreholes: a well
and its sidetracks/re-entries (``34_8-14``, ``34_8-14_A``, ``34_8-14_S``) are one
hole, and the archive stores many files twice under two naming conventions
(byte-identical duplicates). This module puts what belongs together, together:

  - `borehole_id` maps a directory name to its physical well, authoritatively via
    the Sodir parent-well field when the wellbore is in the register, else by a
    conservative sidetrack-suffix heuristic.
  - `group_boreholes` collapses a catalog into `BoreholeGroup`s, each carrying its
    member directories, deduped file inventory, and resolved location + field
    (Sodir first, LAS header as fallback).
  - `dedupe` collapses the double-named exports so inventory counts are real.

Layer note: this sits with `wells.py` (corpus structure), above `io/` and `npd`,
below the wiki. It never imports the web or wiki layers.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import npd as npd_mod
from .wells import Well

# Trailing sidetrack / re-entry tokens in the DISKOS directory form: a lone
# uppercase letter (``_A``), a technical sidetrack (``_T2``), or a re-entry
# (``_R``/``_R1``). Platform wells like ``34_7-P-44`` are unaffected: their last
# segment (``44``) is not one of these tokens.
_SIDETRACK_SUFFIX = re.compile(r"_(?:[A-Z]|T\d+|R\d*)$")
_QB_RE = re.compile(r"^(\d+)_(\d+)-")
_HASH_LIMIT = 50 * 1024 * 1024  # do not hash files bigger than this (seismic)


def quadrant_block(well_id: str) -> tuple[str | None, str | None]:
    """(quadrant, block) from a Norwegian ID, block as ``q_b`` (e.g. ``31_2``).

    Named Danish wells (``ADDA-1``) return (None, None).
    """
    matched = _QB_RE.match(well_id)
    if not matched:
        return (None, None)
    quad, blk = matched.group(1), matched.group(2)
    return (quad, f"{quad}_{blk}")


def borehole_id(well_id: str, records: dict[str, "npd_mod.NpdRecord"] | None = None) -> str:
    """Physical-well ID for a directory name.

    Authoritative when the wellbore is in the Sodir register (its parent ``wlbWell``
    normalised); otherwise strips one trailing sidetrack suffix.
    """
    if records:
        record = npd_mod.match(records, well_id)
        if record is not None:
            return npd_mod.normalize_name(record.well)
    return _SIDETRACK_SUFFIX.sub("", well_id)


def _hash(path: Path) -> str | None:
    try:
        if path.stat().st_size > _HASH_LIMIT:
            return None
        digest = hashlib.sha1()
        digest.update(path.read_bytes())
        return digest.hexdigest()
    except OSError:
        return None


def dedupe(paths: list[Path]) -> tuple[list[Path], list[tuple[Path, Path]]]:
    """Split paths into (unique, duplicate_pairs) by byte-identical content.

    Files are grouped by size first (cheap), only same-size files are hashed.
    The first path in sorted order is kept as canonical; each later identical file
    is reported as ``(canonical, duplicate)``. Files too big to hash are kept.
    """
    by_size: dict[int, list[Path]] = {}
    unhashable: list[Path] = []
    for path in paths:
        try:
            by_size.setdefault(path.stat().st_size, []).append(path)
        except OSError:
            unhashable.append(path)

    unique: list[Path] = list(unhashable)
    duplicates: list[tuple[Path, Path]] = []
    for _size, group in by_size.items():
        if len(group) == 1:
            unique.append(group[0])
            continue
        seen: dict[str, Path] = {}
        for path in sorted(group):
            digest = _hash(path)
            if digest is None:
                unique.append(path)
                continue
            if digest in seen:
                duplicates.append((seen[digest], path))
            else:
                seen[digest] = path
                unique.append(path)
    return sorted(unique), duplicates


@dataclass
class BoreholeGroup:
    """One physical borehole: its member directories, files, and resolved locus."""

    borehole_id: str
    wells: list[Well] = field(default_factory=list)
    files: dict[str, list[Path]] = field(default_factory=dict)
    duplicate_pairs: list[tuple[Path, Path]] = field(default_factory=list)
    lat: float | None = None
    lon: float | None = None
    field_name: str | None = None
    quadrant: str | None = None
    block: str | None = None
    npdid: str | None = None
    npd: "npd_mod.NpdRecord | None" = None
    coord_source: str | None = None  # "npd", "las", or None

    @property
    def well_ids(self) -> list[str]:
        return [w.well_id for w in self.wells]

    @property
    def sidetracks(self) -> list[str]:
        return [wid for wid in self.well_ids if wid != self.borehole_id]

    def count(self, data_type: str) -> int:
        return len(self.files.get(data_type, []))

    def has(self, data_type: str) -> bool:
        return self.count(data_type) > 0


def _merge_and_dedupe(wells: list[Well]) -> tuple[dict[str, list[Path]], list[tuple[Path, Path]]]:
    merged: dict[str, list[Path]] = {}
    for well in wells:
        for data_type, paths in well.files.items():
            merged.setdefault(data_type, []).extend(paths)
    out: dict[str, list[Path]] = {}
    all_dups: list[tuple[Path, Path]] = []
    for data_type, paths in merged.items():
        unique, dups = dedupe(paths)
        out[data_type] = unique
        all_dups.extend(dups)
    return out, all_dups


def _resolve_location(group: BoreholeGroup, records: dict[str, "npd_mod.NpdRecord"]) -> None:
    """Fill lat/lon/field/npdid on the group: Sodir first, LAS header fallback."""
    record = npd_mod.match(records, group.borehole_id)
    if record is None:
        for well_id in group.well_ids:
            record = npd_mod.match(records, well_id)
            if record is not None:
                break
    if record is not None:
        group.npd = record
        group.lat, group.lon = record.lat, record.lon
        group.field_name = record.field
        group.npdid = record.npdid
        if record.lat is not None:
            group.coord_source = "npd"
        return

    # Fallback: read the location out of a member's LAS header.
    from .geo import in_norwegian_shelf, parse_dms
    from .io.las import read_las_header

    for well in group.wells:
        for las in well.files.get("logs", []):
            header = read_las_header(las)
            if not header:
                continue
            lat = parse_dms(header.get("lat_dms"))
            lon = parse_dms(header.get("lon_dms"))
            # Only trust a LAS coordinate that lands on the shelf: many headers
            # hold null sentinels, UTM, or wrong-hemisphere values.
            if in_norwegian_shelf(lat, lon):
                group.lat, group.lon = lat, lon
                group.field_name = group.field_name or header.get("field")
                group.coord_source = "las"
                return
            group.field_name = group.field_name or header.get("field")


def group_boreholes(
    catalog: dict[str, Well],
    records: dict[str, "npd_mod.NpdRecord"] | None = None,
) -> dict[str, BoreholeGroup]:
    """Collapse a well catalog into located, deduped `BoreholeGroup`s.

    Works with or without the Sodir register: given ``records`` identity/location
    are authoritative; without them grouping uses the sidetrack heuristic and
    location falls back to LAS headers.
    """
    records = records or {}
    groups: dict[str, BoreholeGroup] = {}
    for well_id, well in catalog.items():
        bid = borehole_id(well_id, records)
        group = groups.get(bid)
        if group is None:
            quad, blk = quadrant_block(bid)
            group = BoreholeGroup(borehole_id=bid, quadrant=quad, block=blk)
            groups[bid] = group
        group.wells.append(well)

    for group in groups.values():
        group.wells.sort(key=lambda w: w.well_id)
        group.files, group.duplicate_pairs = _merge_and_dedupe(group.wells)
        _resolve_location(group, records)
    return groups
