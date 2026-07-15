"""NPD / Sodir FactPages: the authoritative wellbore register.

The Norwegian Offshore Directorate (Sodir, formerly NPD) publishes every
Norwegian wellbore as public CSV tables. Each row carries the authoritative
identity and location that the DISKOS mirror's files only patchily contain:

  - ``wlbWellboreName`` the full wellbore name, e.g. ``34/8-14 A``
  - ``wlbWell``         the parent well, e.g. ``34/8-14`` (this is how a sidetrack
                        is officially attached to its physical well)
  - ``wlbField``        the field, e.g. ``OSELVAR``
  - ``wlbNsDecDeg`` / ``wlbEwDecDeg``  surface lat/lon in decimal degrees (WGS84)
  - ``wlbNpdidWellbore``  the stable numeric ID also referenced by the strat table

We join to it by normalising the wellbore name to the DISKOS directory form
(``34/8-14 A`` -> ``34_8-14_A``). Wells not in the register (named Danish wells
like ``ADDA-1``) fall back to LAS-header coordinates elsewhere.

The download is one public fetch, cached on disk. No secrets, no auth.
"""

from __future__ import annotations

import csv
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path

# Sodir CSV export endpoint (one table per file).
_BASE = "https://factpages.sodir.no/public?/Factpages/external/tableview"
_SUFFIX = (
    "&rs:Command=Render&rc:Toolbar=false&rc:Parameters=f"
    "&IpAddress=not_used&CultureCode=en&rs:Format=CSV&Top100=false"
)
# Cover exploration + development first (the wells we actually mirror); the two
# smaller tables are best-effort and simply skipped if the endpoint 404s.
DEFAULT_TABLES = (
    "wellbore_exploration_all",
    "wellbore_development_all",
    "wellbore_shallow_all",
    "wellbore_other_all",
)


@dataclass(frozen=True)
class NpdRecord:
    """One wellbore's authoritative facts from the Sodir register."""

    wellbore_name: str
    well: str  # parent well name (sidetracks share it)
    field: str | None
    lat: float | None
    lon: float | None
    npdid: str | None
    well_type: str | None
    operator: str | None
    purpose: str | None
    content: str | None


def _url(table: str) -> str:
    return f"{_BASE}/{table}{_SUFFIX}"


def normalize_name(name: str) -> str:
    """Map a Sodir wellbore/well name to the DISKOS directory form.

    ``34/8-14 A`` -> ``34_8-14_A``; ``1/3-A-1 H`` -> ``1_3-A-1_H``.
    """
    collapsed = re.sub(r"\s+", "_", str(name).strip())
    return collapsed.replace("/", "_")


def fetch_factpages(dest_dir: str | Path, tables=DEFAULT_TABLES, timeout: int = 120) -> list[Path]:
    """Download the wellbore CSV tables into ``dest_dir``. Returns written paths.

    Best-effort per table: a table that fails to download is skipped, not fatal,
    so a register refresh never leaves you with nothing.
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for table in tables:
        target = dest_dir / f"{table}.csv"
        try:
            request = urllib.request.Request(_url(table), headers={"User-Agent": "diskosAI/0.1"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = response.read()
            if data:
                target.write_bytes(data)
                written.append(target)
        except Exception:
            continue
    return written


def _num(value: str | None) -> float | None:
    if not value:
        return None
    try:
        out = float(value)
    except ValueError:
        return None
    return out if out != 0.0 else None


def _pick(row: dict, *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value.strip()
    return None


def _record_from_row(row: dict) -> NpdRecord | None:
    name = _pick(row, "wlbWellboreName")
    if not name:
        return None
    return NpdRecord(
        wellbore_name=name,
        well=_pick(row, "wlbWell") or name,
        field=_pick(row, "wlbField"),
        lat=_num(_pick(row, "wlbNsDecDeg")),
        lon=_num(_pick(row, "wlbEwDecDeg")),
        npdid=_pick(row, "wlbNpdidWellbore"),
        well_type=_pick(row, "wlbWellType"),
        operator=_pick(row, "wlbDrillingOperator"),
        purpose=_pick(row, "wlbPurpose", "wlbPurposePlanned"),
        content=_pick(row, "wlbContent"),
    )


def load_factpages(npd_dir: str | Path) -> dict[str, NpdRecord]:
    """Load every ``*.csv`` in ``npd_dir`` into {normalized wellbore name -> record}.

    Returns {} if the directory is absent, so callers degrade to file-derived
    coordinates without special-casing "no register downloaded yet".
    """
    npd_dir = Path(npd_dir)
    if not npd_dir.is_dir():
        return {}
    records: dict[str, NpdRecord] = {}
    for csv_path in sorted(npd_dir.glob("*.csv")):
        with open(csv_path, encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                record = _record_from_row(row)
                if record is not None:
                    records.setdefault(normalize_name(record.wellbore_name), record)
    return records


def match(records: dict[str, NpdRecord], well_id: str) -> NpdRecord | None:
    """Find the register record for a DISKOS directory name, or None.

    Tries an exact normalized match, then a case-insensitive one.
    """
    if not records:
        return None
    key = normalize_name(well_id)
    if key in records:
        return records[key]
    lowered = key.lower()
    for name, record in records.items():
        if name.lower() == lowered:
            return record
    return None
