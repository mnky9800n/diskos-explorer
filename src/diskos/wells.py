"""Borehole catalog: discover wells from the real DISKOS tree.

The real archive (confirmed against lambda-scalar) is one top-level directory per
well (2700+ of them), named by well ID: Norwegian (``35_10-8_S``, ``6603_12-1``,
``1_3-K-3``) and named Danish wells (``ADDA-1``, ``A-1X``). Inside each well the
data is foldered by category (``LOGS``, ``WELL_PATH``, ``WELL_SEISMIC``,
``GEOLOGY``, ``DRILLING``, ``Reports``, ``ROCK_AND_CORE`` ...).

So the well ID is the directory name (not derived from filenames), and a file's
data type comes from its category folder plus its name/extension. Note that a
``.LAS`` under ``WELL_PATH`` is a deviation survey, not a petrophysical log, and a
``.ASC`` here is a Tigress export (well path / checkshot), not StrataBugs
palynology. Curated StrataBugs palynology is a separate bring-your-own input, not
part of this mirror.

Because there are thousands of wells, listing them is kept cheap (top-level dirs
only); a well's files are classified on demand by recursing that one well.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Top-level entries that are not wells.
ADMIN_DIRS = {
    "000-README", "001_GENERAL_WELL_INFORMATION", "002_OTHER", "003-tmp", "00-Admin",
}

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".cr2", ".bmp", ".gif"}
SEISMIC_EXTS = {".segy", ".sgy"}
DOC_EXTS = {".pdf", ".doc", ".docx"}

# Data-type buckets, in display order.
DATA_TYPES = ["logs", "seismic", "deviation", "geology", "images", "geochem", "core", "other"]


def classify(rel_dir: str, name: str) -> str:
    """Classify a file into a data type from its within-well path and name.

    ``rel_dir`` is the file's directory relative to the well root (may be nested,
    e.g. ``Tapelogs/Deviation_Position_data``); ``name`` is the file name.
    """
    path = rel_dir.lower().replace("\\", "/")
    name_l = name.lower()
    ext = os.path.splitext(name_l)[1]

    if ext in IMAGE_EXTS:
        return "images"
    if ext in SEISMIC_EXTS:
        return "seismic"
    if ext == ".las":
        # LAS under a well-path/deviation folder is a survey, not a log.
        if "well_path" in path or "wellpath" in name_l or "deviation" in path or "_dev" in name_l:
            return "deviation"
        return "logs"
    if ext in DOC_EXTS:
        return "geology"  # GEOLOGY / Reports / strat, incl. biostrat (see is_biostrat)
    if ext == ".csv" and any(k in name_l for k in ("qemscan", "toc", "xrf")):
        return "geochem"
    if "rock_and_core" in path:
        return "core"
    if "well_seismic" in path:
        return "seismic"
    if "well_path" in path:
        return "deviation"
    return "other"


def is_biostrat(path: Path) -> bool:
    """Whether a file looks like a biostratigraphy (palynology) report."""
    return "biostrat" in path.name.lower()


@dataclass
class Well:
    """A borehole and its files bucketed by data type."""

    well_id: str
    path: Path
    files: dict[str, list[Path]] = field(default_factory=dict)

    def count(self, data_type: str) -> int:
        return len(self.files.get(data_type, []))

    def has(self, data_type: str) -> bool:
        return self.count(data_type) > 0

    def total(self) -> int:
        return sum(len(v) for v in self.files.values())

    def counts(self) -> dict[str, int]:
        return {t: self.count(t) for t in DATA_TYPES if self.count(t)}


def list_well_ids(root: Path) -> list[str]:
    """Cheap: every top-level well directory name, admin dirs excluded, sorted."""
    return sorted(
        p.name for p in root.iterdir()
        if p.is_dir() and p.name not in ADMIN_DIRS
    )


def well_files(root: Path, well_id: str) -> Well:
    """Recurse a single well and bucket its files by data type."""
    well_dir = root / well_id
    if not well_dir.is_dir() or well_id in ADMIN_DIRS:
        raise KeyError(f"Well {well_id!r} not found under {root}.")
    files: dict[str, list[Path]] = {}
    for f in sorted(well_dir.rglob("*")):
        if not f.is_file():
            continue
        rel_dir = str(f.parent.relative_to(well_dir))
        files.setdefault(classify(rel_dir, f.name), []).append(f)
    return Well(well_id=well_id, path=well_dir, files=files)


def catalog(root: Path) -> dict[str, Well]:
    """Full catalog (recurses every well). Fine for tests and offline use; the web
    app uses ``list_well_ids`` + ``well_files`` to stay fast on a mounted tree."""
    return {wid: well_files(root, wid) for wid in list_well_ids(root)}
