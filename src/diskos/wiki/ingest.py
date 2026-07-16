"""Ingest per-well pipeline artifacts into the wiki (Layer B, the larger context).

This is the deterministic core of the ingest loop from projectNotes: read a
source (a per-well palynology CSV), write/refresh its entity page, update the
index, and append to the log. No model is required for this structured pass, so
it is fully testable. An optional LLMClient can enrich the page with prose
synthesis, but the factual summary stands on its own.

No em dashes in generated content (house rule).
"""

from __future__ import annotations

import hashlib
import json
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


# --- Whole-archive borehole + field pages (built from a dossier) ------------

def field_slug(name: str) -> str:
    """Filesystem/link-safe slug for a field or block name."""
    return name.replace(" ", "_").replace("/", "_")


def dossier_hash(dossier: dict) -> str:
    """Stable hash of a dossier, so an unchanged borehole is skipped on rebuild."""
    payload = json.dumps(dossier, sort_keys=True, default=str)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def _locus_line(loc: dict, npd: dict | None, sidetracks: list[str]) -> str:
    parts = []
    if loc.get("field"):
        parts.append(f"{loc['field']} field")
    if loc.get("block"):
        parts.append(f"block {loc['block']}")
    if loc.get("lat") is not None and loc.get("lon") is not None:
        src = loc.get("coord_source") or "unknown"
        parts.append(f"{loc['lat']:.4f} N {loc['lon']:.4f} E (source: {src})")
    if npd:
        meta = ", ".join(v for v in (npd.get("well_type"), npd.get("purpose"), npd.get("content")) if v)
        if meta:
            parts.append(meta.lower())
    if npd and npd.get("operator"):
        parts.append(f"operator {npd['operator']}")
    if sidetracks:
        parts.append(f"includes sidetrack {', '.join(sidetracks)}")
    return ". ".join(parts) + "." if parts else "Location not resolved from the mirror or NPD."


def render_borehole_page(dossier: dict, on_date: str, prose: str = "") -> str:
    """Render an IODP-style borehole page from a dossier. Model-free by default."""
    bid = dossier["borehole_id"]
    loc = dossier["location"]
    npd = dossier.get("npd")
    lines = [
        "---",
        "type: borehole",
        f"borehole_id: {bid}",
        f"well_ids: [{', '.join(dossier['well_ids'])}]",
        f"field: {loc.get('field') or ''}",
        f"block: {loc.get('block') or ''}",
        f"quadrant: {loc.get('quadrant') or ''}",
        f"lat: {loc.get('lat') if loc.get('lat') is not None else ''}",
        f"lon: {loc.get('lon') if loc.get('lon') is not None else ''}",
        f"npdid: {loc.get('npdid') or ''}",
        f"coord_source: {loc.get('coord_source') or ''}",
        f"sidetracks: [{', '.join(dossier['sidetracks'])}]",
        f"updated: {on_date}",
        f"dossier_hash: {dossier_hash(dossier)}",
        "tags: [borehole, well]",
        "---",
        "",
        f"# Borehole {bid}",
        "",
        _locus_line(loc, npd, dossier["sidetracks"]),
        "",
        "## Overview",
        "",
        prose or "No synthesized overview yet (deterministic facts below).",
        "",
        "## Data available",
        "",
    ]
    inv = dossier["inventory"]
    if inv:
        for data_type, count in inv.items():
            names = ", ".join(dossier["inventory_files"].get(data_type, []))
            lines.append(f"- {data_type} ({count}): {names}")
        if dossier["duplicate_count"]:
            lines.append(f"- ({dossier['duplicate_count']} byte-identical duplicate files collapsed)")
    else:
        lines.append("No catalogued files in the mirror.")

    lines += ["", "## Well logs", ""]
    if dossier["logs"]:
        for log in dossier["logs"]:
            depth = f"{log['depth'][0]:.0f}-{log['depth'][1]:.0f} m" if log.get("depth") else "depth unknown"
            entry = f"- {log['file']}: curves [{', '.join(log['mnemonics'][:24])}]; {depth}"
            if log.get("gamma"):
                g = log["gamma"]
                entry += f"; gamma {g['curve']} {g['min']:.0f}/{g['mean']:.0f}/{g['max']:.0f} API"
            lines.append(entry)
    else:
        lines.append("No well logs in the mirror.")

    lines += ["", "## Palynology", ""]
    paly = dossier.get("palynology")
    if paly:
        lines.append(f"Palynology from `{paly.get('source', 'CSV')}`, {paly['n_depths']} sampled depths.")
        lines += ["", "| species | total count |", "| --- | --- |"]
        for species in paly["species"]:
            lines.append(f"| [[{species.replace('_', ' ')}]] | {paly['totals'][species]:.0f} |")
        if not paly["species"]:
            lines.append("| (none matched) | |")
    else:
        lines.append("No palynology data ingested for this borehole.")

    lines += ["", "## Reports", ""]
    if dossier["reports"]:
        for rep in dossier["reports"]:
            tag = "biostrat" if rep["biostrat"] else "report"
            note = ""
            if rep.get("interval"):
                note = f" (studied {rep['interval'][0]:.0f}-{rep['interval'][1]:.0f} m)"
            elif not rep.get("has_text"):
                note = " (scanned, no extractable text)"
            lines.append(f"- [{tag}] {rep['file']}{note}")
    else:
        lines.append("No report in the local mirror.")

    lines += ["", "## Related", ""]
    if dossier["sidetracks"]:
        lines.append("- Sidetracks: " + ", ".join(f"[[well_{s}]]" for s in dossier["sidetracks"]))
    if loc.get("field"):
        lines.append(f"- Field: [[field_{field_slug(loc['field'])}]]")
    elif loc.get("block"):
        lines.append(f"- Block: [[field_{field_slug(loc['block'])}]]")
    if dossier["neighbors"]:
        near = ", ".join(f"[[well_{n['borehole_id']}]] ({n['distance_km']} km)" for n in dossier["neighbors"])
        lines.append(f"- Nearby: {near}")
    if not (dossier["sidetracks"] or loc.get("field") or loc.get("block") or dossier["neighbors"]):
        lines.append("No related wells resolved.")

    lines += ["", "## Gaps and confidence", ""]
    lines += _gap_notes(dossier)
    lines.append("")
    return "\n".join(lines)


def _gap_notes(dossier: dict) -> list[str]:
    loc = dossier["location"]
    notes = []
    src = loc.get("coord_source")
    if src == "npd":
        notes.append("- Location is authoritative (NPD FactPages).")
    elif src == "las":
        notes.append("- Location is from a LAS header, not NPD; treat as approximate.")
    else:
        notes.append("- No coordinates resolved for this borehole.")
    if not dossier["inventory"].get("core"):
        notes.append("- No core in the mirror (gamma cannot be calibrated to core here).")
    if not dossier["reports"]:
        notes.append("- No report present; interpretation rests on data files alone.")
    notes.append("- Absence reflects what is in the local mirror, not what exists.")
    return notes


def borehole_prompt(dossier: dict) -> str:
    """Prompt for the LLM to write the Overview from the dossier's facts only."""
    facts = json.dumps(
        {k: v for k, v in dossier.items() if k != "report_excerpt"},
        default=str,
    )
    excerpt = dossier.get("report_excerpt") or "(no report text)"
    return (
        f"Write a 3 to 5 sentence overview of Norwegian borehole {dossier['borehole_id']} "
        f"for a geologist, using only these facts. State what data exists, the field and "
        f"location, and what is missing. Do not invent species, ages, or numbers not present. "
        f"No em dashes.\n\nFACTS (JSON):\n{facts}\n\nREPORT EXCERPTS:\n{excerpt[:3000]}"
    )


def ingest_borehole(
    dossier: dict,
    wiki_dir: str | Path,
    on_date: str | None = None,
    client=None,
    force: bool = False,
) -> Path | None:
    """Write one borehole page. Returns its path, or None if skipped (unchanged).

    Resumable: if the page exists and its stored dossier_hash matches, it is left
    alone unless ``force``. With ``client`` (an LLMClient) the Overview is authored
    by the model; without one a deterministic placeholder stands in.
    """
    wiki_dir = Path(wiki_dir)
    on_date = on_date or _date.today().isoformat()
    bid = dossier["borehole_id"]
    relpath = f"{ENTITIES}/well_{bid}.md"
    page_path = wiki_dir / relpath

    new_hash = dossier_hash(dossier)
    if not force and page_path.exists():
        existing = page_path.read_text(encoding="utf-8")
        if f"dossier_hash: {new_hash}" in existing:
            return None

    prose = ""
    if client is not None:
        try:
            prose = client.ask(borehole_prompt(dossier), max_tokens=400, temperature=0.2).strip()
        except Exception:
            prose = ""

    page = render_borehole_page(dossier, on_date, prose)
    (wiki_dir / ENTITIES).mkdir(parents=True, exist_ok=True)
    page_path.write_text(page, encoding="utf-8")

    loc = dossier["location"]
    where = loc.get("field") or (f"block {loc['block']}" if loc.get("block") else "location unknown")
    upsert_index_entry(
        wiki_dir, "Boreholes", relpath, f"borehole {bid}",
        f"{where}; " + ", ".join(f"{t} {c}" for t, c in dossier["inventory"].items()),
    )
    append_log(wiki_dir, on_date, "ingest", f"borehole {bid}")
    return page_path


def render_field_page(area_key: str, display: str, members: list[dict], on_date: str, prose: str = "") -> str:
    """Render an area (field or block) page aggregating its member boreholes."""
    slug = field_slug(area_key)
    lines = [
        "---",
        "type: field",
        f"field: {area_key}",
        f"n_boreholes: {len(members)}",
        f"updated: {on_date}",
        "tags: [field, area]",
        "---",
        "",
        f"# {display}",
        "",
        "## Overview",
        "",
        prose or f"{display} groups {len(members)} boreholes from the mirror (facts below).",
        "",
        "## Boreholes",
        "",
        "| borehole | data | reports | core |",
        "| --- | --- | --- | --- |",
    ]
    for m in sorted(members, key=lambda d: d["borehole_id"]):
        inv = m["inventory"]
        data = ", ".join(f"{t} {c}" for t, c in inv.items()) or "none"
        reports = "yes" if m["reports"] else "-"
        core = "yes" if inv.get("core") else "-"
        lines.append(f"| [[well_{m['borehole_id']}]] | {data} | {reports} | {core} |")

    with_core = [m["borehole_id"] for m in members if m["inventory"].get("core")]
    lines += ["", "## Gaps and confidence", ""]
    if with_core:
        lines.append(f"- Core control at: {', '.join('[[well_'+b+']]' for b in with_core)} (gamma-core calibration anchors).")
    else:
        lines.append("- No core in any member borehole; gamma cannot be tied to core in this area.")
    lines.append("- Coverage reflects the local mirror, which is partial and growing.")
    lines.append("")
    return "\n".join(lines)


def field_prompt(display: str, members: list[dict]) -> str:
    brief = [
        {
            "borehole": m["borehole_id"],
            "field": m["location"].get("field"),
            "inventory": m["inventory"],
            "has_report": bool(m["reports"]),
        }
        for m in members
    ]
    # Pass the tallies explicitly: models miscount list items, so never let the
    # model derive these numbers itself.
    counts = {
        "boreholes": len(members),
        "with_report": sum(1 for m in members if m["reports"]),
        "with_core": sum(1 for m in members if m["inventory"].get("core")),
        "with_logs": sum(1 for m in members if m["inventory"].get("logs")),
    }
    return (
        f"Write a 3 to 5 sentence overview of {display}, a group of Norwegian boreholes, "
        f"for a geologist. There are exactly {counts['boreholes']} boreholes: "
        f"{counts['with_logs']} have logs, {counts['with_report']} have a report, "
        f"{counts['with_core']} have core. Use these exact counts, do not state any other "
        f"totals. Note what data exists across them and what is missing. Invent nothing. "
        f"No em dashes.\n\nCOUNTS (authoritative):\n{json.dumps(counts)}\n\n"
        f"MEMBERS (JSON):\n{json.dumps(brief, default=str)}"
    )


def ingest_field(
    area_key: str,
    display: str,
    members: list[dict],
    wiki_dir: str | Path,
    on_date: str | None = None,
    client=None,
) -> Path:
    """Write one area (field/block) page aggregating its member boreholes."""
    wiki_dir = Path(wiki_dir)
    on_date = on_date or _date.today().isoformat()
    slug = field_slug(area_key)
    relpath = f"{ENTITIES}/field_{slug}.md"

    prose = ""
    if client is not None:
        try:
            prose = client.ask(field_prompt(display, members), max_tokens=400, temperature=0.2).strip()
        except Exception:
            prose = ""

    page = render_field_page(area_key, display, members, on_date, prose)
    (wiki_dir / ENTITIES).mkdir(parents=True, exist_ok=True)
    (wiki_dir / relpath).write_text(page, encoding="utf-8")
    upsert_index_entry(
        wiki_dir, "Fields", relpath, display, f"{len(members)} boreholes",
    )
    append_log(wiki_dir, on_date, "ingest", f"field {display}")
    return wiki_dir / relpath
