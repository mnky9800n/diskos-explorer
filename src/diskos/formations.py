"""SODIR / NPD wellbore formation tops (lithostratigraphy).

For each wellbore, the depth where every named rock unit (group / formation)
begins and ends. Sourced from the same public FactPages system as the wellbore
register (``npd.py``). A formation is a mappable unit of rock distinct from what
is above and below it, so these tops are what a geologist reads a log against
(issue #22) and are the depth-to-formation lookup the analytical assistant needs
(issue #24).

Joins to our wells by normalizing the wellbore name to the directory form
(``31/2-1`` -> ``31_2-1``), exactly like the register.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from . import npd as npd_mod

FORMATION_TABLE = "wellbore_formation_top"


@dataclass(frozen=True)
class FormationTop:
    """One named unit in a well: its depth range and stratigraphic level."""

    name: str
    level: str  # GROUP / FORMATION / MEMBER / SUBGROUP
    top: float
    bottom: float | None


def fetch(dest_dir: str | Path, timeout: int = 120) -> list[Path]:
    """Download the formation-tops CSV into ``dest_dir`` (best-effort)."""
    return npd_mod.fetch_factpages(dest_dir, tables=(FORMATION_TABLE,), timeout=timeout)


def _num(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_formation_tops(npd_dir: str | Path) -> dict[str, list[FormationTop]]:
    """Load the tops table into {normalized wellbore name -> [FormationTop]}.

    Returns {} if the table has not been fetched, so callers degrade to plots
    without formation labels rather than erroring.
    """
    path = Path(npd_dir) / f"{FORMATION_TABLE}.csv"
    if not path.is_file():
        return {}
    out: dict[str, list[FormationTop]] = {}
    with open(path, encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            top = _num(row.get("lsuTopDepth"))
            name = (row.get("lsuName") or "").strip()
            if top is None or not name:
                continue
            entry = FormationTop(
                name=name,
                level=(row.get("lsuLevel") or "").strip(),
                top=top,
                bottom=_num(row.get("lsuBottomDepth")),
            )
            out.setdefault(npd_mod.normalize_name(row["wlbName"]), []).append(entry)
    for tops in out.values():
        tops.sort(key=lambda t: t.top)
    return out


def wells_by_formation(tops_by_well: dict[str, list[FormationTop]]) -> dict[str, set[str]]:
    """Invert the tops table: {formation name -> set of wellbore names that have it}."""
    out: dict[str, set[str]] = {}
    for well, tops in tops_by_well.items():
        for unit in tops:
            out.setdefault(unit.name, set()).add(well)
    return out


def all_formations(tops_by_well: dict[str, list[FormationTop]], level: str | None = None) -> list[dict]:
    """Distinct formations with their level and how many wells have each, most common first."""
    counts: dict[str, int] = {}
    levels: dict[str, str] = {}
    for tops in tops_by_well.values():
        seen: set[str] = set()
        for unit in tops:
            if level and unit.level != level.upper():
                continue
            if unit.name in seen:
                continue
            seen.add(unit.name)
            counts[unit.name] = counts.get(unit.name, 0) + 1
            levels[unit.name] = unit.level
    return sorted(
        ({"name": n, "level": levels[n], "count": counts[n]} for n in counts),
        key=lambda d: (-d["count"], d["name"]),
    )


def tops_for(
    tops_by_well: dict[str, list[FormationTop]],
    borehole_id: str,
    well_ids=(),
    level: str | None = None,
) -> list[FormationTop]:
    """Formation tops for a borehole (its parent, else any member), optionally
    restricted to one level (e.g. ``"FORMATION"``)."""
    found: list[FormationTop] = []
    for key in (borehole_id, *well_ids):
        norm = npd_mod.normalize_name(key)
        if norm in tops_by_well:
            found = tops_by_well[norm]
            break
    if level:
        found = [t for t in found if t.level == level.upper()]
    return found
