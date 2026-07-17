"""Analytical assistant: compare the raw multi-log signal of a formation or a
depth interval across wells, then have the model explain how they differ (#24).

The compute is deterministic: for each well, resolve the depth window (a named
formation looked up in that well's tops, or an explicit interval), slice every
available log family (gamma, density, neutron, sonic, resistivity), and compute
per-curve statistics. Those numbers, not the raw curves, are handed to the model,
which is asked to describe how the signatures differ and cite the values. This
catches the subtleties the eye misses in a plot, without letting the model invent
numbers.
"""

from __future__ import annotations

# Log families and the mnemonics that stand for them, in preference order.
CURVE_FAMILIES: dict[str, tuple[str, ...]] = {
    "gamma": ("GR", "HGR", "CGR", "SGR", "GRD", "GRR"),
    "density": ("RHOB", "DEN", "HRHOB", "DENB", "ZDEN"),
    "neutron": ("NPHI", "NEU", "HNPHI", "TNPH", "CN"),
    "sonic": ("DT", "AC", "DTC", "HDT", "SON", "DTCO"),
    "resistivity_deep": ("RDEP", "RD", "ILD", "LLD", "RT", "HRD", "AT90"),
    "resistivity_med": ("RMED", "RM", "ILM", "LLM", "HRM", "AT30"),
}


def pick_curves(columns) -> dict[str, str]:
    """Map each present log family to its best-available mnemonic in ``columns``."""
    present = set(columns)
    picks: dict[str, str] = {}
    for family, mnemonics in CURVE_FAMILIES.items():
        for mnemonic in mnemonics:
            if mnemonic in present:
                picks[family] = mnemonic
                break
    return picks


def _stats(series) -> dict:
    import numpy as np

    values = series.to_numpy(dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return {}
    return {
        "n": int(values.size),
        "mean": round(float(values.mean()), 2),
        "min": round(float(values.min()), 2),
        "max": round(float(values.max()), 2),
        "std": round(float(values.std()), 2),
    }


def _window(well, formation, top, bottom, tops_by_well, records):
    """Resolve the depth window for a well: a named formation from its own tops,
    or the explicit interval. Returns (label, top, bottom) or None."""
    if formation:
        from .. import formations
        from ..boreholes import borehole_id

        bid = borehole_id(well.well_id, records)
        want = formation.strip().upper()
        for unit in formations.tops_for(tops_by_well, bid, [well.well_id]):
            if unit.name.upper() == want and unit.bottom is not None:
                return (unit.name, unit.top, unit.bottom)
        return None
    if top is not None and bottom is not None:
        return (f"{top:.0f}-{bottom:.0f} m", float(top), float(bottom))
    return None


def compute(wells, formation=None, top=None, bottom=None, tops_by_well=None, records=None) -> dict:
    """Per-well multi-log statistics over a formation/interval. Model-free."""
    from ..welllog import curves as wl

    tops_by_well = tops_by_well or {}
    records = records or {}
    per_well: list[dict] = []
    missing: list[str] = []
    for well in wells:
        window = _window(well, formation, top, bottom, tops_by_well, records)
        las_files = well.files.get("logs", [])
        if window is None or not las_files:
            missing.append(well.well_id)
            continue
        label, wtop, wbot = window
        try:
            df = wl.read_las(las_files[0])
        except Exception:
            missing.append(well.well_id)
            continue
        depth = df.index.to_numpy(dtype=float)
        mask = (depth >= wtop) & (depth <= wbot)
        curves: dict[str, dict] = {}
        for family, mnemonic in pick_curves(df.columns).items():
            stats = _stats(df[mnemonic][mask])
            if stats:
                curves[family] = {"mnemonic": mnemonic, **stats}
        if curves:
            per_well.append({"well_id": well.well_id, "interval": [wtop, wbot], "curves": curves})
        else:
            missing.append(well.well_id)
    target = formation or (per_well[0]["interval"] if per_well else "interval")
    return {"target": target, "per_well": per_well, "missing": missing}


def analyze_prompt(result: dict) -> str:
    import json

    return (
        f"Compare the downhole-log signature of {result['target']} across these Norwegian "
        f"wells for a geologist. For each well you are given per-curve statistics "
        f"(mean/min/max/std) over that formation or interval: gamma (clean sand vs shale), "
        f"density and neutron (porosity/lithology), sonic (transit time), and resistivity "
        f"(possible hydrocarbons). In 4 to 6 sentences describe how the signatures differ "
        f"between the wells and what that suggests, citing the numbers. Use only these "
        f"values, invent nothing. No em dashes.\n\nDATA (JSON):\n{json.dumps(result['per_well'])}"
    )


def analyze(wells, formation=None, top=None, bottom=None, tops_by_well=None, records=None, client=None) -> dict:
    """Compute the stats and, if a model client is given, add a grounded narrative."""
    result = compute(wells, formation, top, bottom, tops_by_well, records)
    narrative = ""
    if client is not None and result["per_well"]:
        try:
            narrative = client.ask(analyze_prompt(result), max_tokens=500, temperature=0.2).strip()
        except Exception:
            narrative = ""
    result["narrative"] = narrative
    return result
