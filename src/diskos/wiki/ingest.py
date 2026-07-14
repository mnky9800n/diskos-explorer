"""Ingest per-well pipeline artifacts into the wiki (Layer B, the larger context).

This is the deterministic core of the ingest loop from projectNotes: read a
source (a per-well palynology CSV), write/refresh its entity page, update the
index, and append to the log. No model is required for this structured pass, so
it is fully testable. An optional LLMClient can enrich the page with prose
synthesis, but the factual summary stands on its own.

No em dashes in generated content (house rule).
"""

from __future__ import annotations

from datetime import date as _date
from pathlib import Path

import pandas as pd

from ..palyno.plot import palyno_well_key_from_fname
from .index import append_log, upsert_index_entry

ENTITIES = "entities"


def summarize_well_csv(csv_path: str | Path) -> dict:
    """Summarize a per-well palynology CSV (depth x species) for the wiki."""
    df = pd.read_csv(csv_path)
    depth = pd.to_numeric(df.get("depth"), errors="coerce")
    cnt_cols = [c for c in df.columns if c.endswith("_cnt")]
    totals = {
        c[:-4]: float(pd.to_numeric(df[c], errors="coerce").sum(min_count=1))
        for c in cnt_cols
    }
    totals = {k: v for k, v in totals.items() if pd.notna(v)}
    return {
        "n_depths": int(depth.notna().sum()),
        "depth_min": float(depth.min()) if depth.notna().any() else None,
        "depth_max": float(depth.max()) if depth.notna().any() else None,
        "species": sorted(totals),
        "totals": totals,
    }


def render_well_page(well_id: str, summary: dict, source_name: str, on_date: str, prose: str = "") -> str:
    """Render an entity-page markdown string for a well."""
    depth_min, depth_max = summary["depth_min"], summary["depth_max"]
    depth_range = (
        f"{depth_min:.1f} to {depth_max:.1f} m" if depth_min is not None else "unknown"
    )
    lines = [
        "---",
        "type: well",
        f"well_id: {well_id}",
        f"source: {source_name}",
        f"updated: {on_date}",
        "tags: [well, palynology]",
        "---",
        "",
        f"# Well {well_id}",
        "",
        f"Palynology summary from `{source_name}`. Sampled at {summary['n_depths']} "
        f"depths over {depth_range}.",
        "",
        "## Target species (total counts)",
        "",
        "| species | total count |",
        "| --- | --- |",
    ]
    for species in summary["species"]:
        total = summary["totals"][species]
        pretty = species.replace("_", " ")
        lines.append(f"| [[{pretty}]] | {total:.0f} |")
    if not summary["species"]:
        lines.append("| (none matched) | |")

    if prose:
        lines += ["", "## Notes", "", prose]

    lines.append("")
    return "\n".join(lines)


def ingest_well_csv(
    csv_path: str | Path,
    wiki_dir: str | Path,
    well_id: str | None = None,
    on_date: str | None = None,
    client=None,
) -> Path:
    """Ingest one per-well CSV: write its entity page, update index.md and log.md.

    Returns the path of the entity page written. If ``client`` (an LLMClient) is
    given, a short prose synthesis is added to the page; otherwise the structured
    summary stands alone.
    """
    csv_path = Path(csv_path)
    wiki_dir = Path(wiki_dir)
    well_id = well_id or palyno_well_key_from_fname(csv_path.name)
    on_date = on_date or _date.today().isoformat()

    summary = summarize_well_csv(csv_path)

    prose = ""
    if client is not None:
        prose = client.ask(
            f"In 2-3 sentences, summarize the palynology of well {well_id} given these "
            f"target-species total counts over {summary['n_depths']} depths: {summary['totals']}."
        )

    page = render_well_page(well_id, summary, csv_path.name, on_date, prose)
    entities_dir = wiki_dir / ENTITIES
    entities_dir.mkdir(parents=True, exist_ok=True)
    relpath = f"{ENTITIES}/well_{well_id}.md"
    (wiki_dir / relpath).write_text(page, encoding="utf-8")

    n_species = len(summary["species"])
    dmin, dmax = summary["depth_min"], summary["depth_max"]
    depth_note = f"{dmin:.0f} to {dmax:.0f} m" if dmin is not None else "no depths"
    upsert_index_entry(
        wiki_dir, "Entities", relpath, f"well {well_id}",
        f"{n_species} target species, {depth_note}",
    )
    append_log(wiki_dir, on_date, "ingest", f"well {well_id} palynology")
    return wiki_dir / relpath
