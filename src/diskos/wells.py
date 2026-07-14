"""Borehole catalog: discover wells from the DISKOS tree.

This is the generalization backbone. Instead of hardcoding well IDs and intervals
(as Jack's notebooks do), we scan the data root, derive a well ID from each file,
and record which data types every well has. Every analysis stage then addresses
wells by ID or sweeps them all.

Discovery is layout-agnostic on purpose: it finds files by extension anywhere
under the root and derives the well ID from the file name, so it does not depend
on a specific folder structure (which we have not yet confirmed on lambda-scalar).
The well ID is the base Norwegian wellbore name, e.g. ``35/10-8`` -> ``35_10-8``,
with any sidetrack suffix (``_S``, ``_R`` ...) stripped so a well's palynology and
logs group together.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# Base wellbore name: quadrant _ block - serial. Quadrant may be 1-4 digits
# (e.g. 7_11-1 in the North Sea, 6608_10-1 in the Norwegian Sea).
_WELL_ID_RE = re.compile(r"\d{1,4}_\d{1,3}-\d+")

# Data-type classification by file.
_PALY_SUFFIXES = {".asc"}
_LOG_SUFFIXES = {".las"}


@dataclass
class Well:
    """A borehole and the data files discovered for it."""

    well_id: str
    paly: list[Path] = field(default_factory=list)
    logs: list[Path] = field(default_factory=list)
    xrf: list[Path] = field(default_factory=list)

    def has(self, data_type: str) -> bool:
        return bool(getattr(self, data_type))


def extract_well_id(name: str) -> str | None:
    """Derive the base well ID from a file name or path component.

    Returns None if no wellbore pattern is present.
    """
    match = _WELL_ID_RE.search(name)
    return match.group(0) if match else None


def _classify(path: Path) -> str | None:
    """Return the data-type bucket for a file, or None to ignore it."""
    suffix = path.suffix.lower()
    if suffix in _PALY_SUFFIXES:
        return "paly"
    if suffix in _LOG_SUFFIXES:
        return "logs"
    if suffix == ".csv" and "xrf" in path.name.lower():
        return "xrf"
    return None


def catalog(root: Path) -> dict[str, Well]:
    """Scan ``root`` recursively and return {well_id: Well}.

    Files whose name contains no wellbore pattern, or whose type we do not
    recognize, are skipped.
    """
    wells: dict[str, Well] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        bucket = _classify(path)
        if bucket is None:
            continue
        well_id = extract_well_id(path.name)
        if well_id is None:
            continue
        well = wells.setdefault(well_id, Well(well_id=well_id))
        getattr(well, bucket).append(path)
    return wells


def find_well(root: Path, well_id: str) -> Well:
    """Return a single well's catalog entry, or raise if not found."""
    wells = catalog(root)
    if well_id not in wells:
        known = ", ".join(sorted(wells)) or "(none discovered)"
        raise KeyError(f"Well {well_id!r} not found under {root}. Known wells: {known}")
    return wells[well_id]
