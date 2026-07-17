"""Workflow runner: turn a data source + an instruction into an output artifact.

The first, minimal shape of the workflow idea: a raw data source (a well's log)
feeds a chat instruction, which generates an output note (a plot). This is the
same operation Jack's Well_Logs notebook does, exposed as a wired node flow.

v1 supports one flow, plotting a well's log against depth. The instruction may
name a curve mnemonic; otherwise gamma is used. Richer generative outputs (pick
the chart from the instruction via the model, palynology plots, tables) build on
this same endpoint.
"""

from __future__ import annotations

import base64
import io
import re


_TOPS_CACHE: dict = {}


def _formation_tops(well_id: str):
    """Formation tops (FORMATION level) for a well, cached across calls. [] if none."""
    from .. import formations
    from .. import npd
    from ..boreholes import borehole_id
    from ..config import load_config

    cfg = load_config()
    key = str(cfg.npd_path())
    if key not in _TOPS_CACHE:
        _TOPS_CACHE[key] = (
            formations.load_formation_tops(cfg.npd_path()),
            npd.load_factpages(cfg.npd_path()),
        )
    tops_by_well, records = _TOPS_CACHE[key]
    if not tops_by_well:
        return []
    bid = borehole_id(well_id, records)
    return formations.tops_for(tops_by_well, bid, [well_id], level="FORMATION")


def _figure_to_data_uri(fig) -> str:
    import matplotlib.pyplot as plt

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def plot_log(well, mnemonic: str | None = None, instruction: str = "") -> dict:
    """Plot a well log against depth. Returns {title, image (data URI), mnemonic}."""
    import matplotlib
    matplotlib.use("Agg")

    from ..welllog import curves as wl
    from ..welllog import plot as wlp

    las_files = well.files.get("logs", [])
    if not las_files:
        raise ValueError("this well has no logs to plot")
    df = wl.read_las(las_files[0])

    pick = mnemonic if (mnemonic and mnemonic in df.columns) else None
    if pick is None:
        # let the instruction name a curve, else gamma
        for token in re.findall(r"[A-Za-z]{2,6}", instruction.upper()):
            if token in df.columns:
                pick = token
                break
    if pick is None:
        pick = wl.gamma_column(df)

    series = wl.curve_series(df, pick)
    label = f"{well.well_id}:{pick}"
    tops = _formation_tops(well.well_id)
    fig = wlp.plot_correlation({label: series}, tops_by_label={label: tops} if tops else None)
    return {"title": f"{well.well_id}  {pick} vs depth", "image": _figure_to_data_uri(fig), "mnemonic": pick}


def compare_logs(wells, mnemonic: str | None = None) -> dict:
    """Plot one curve across several wells, side by side, for correlation (#20).

    ``wells`` is a list of Well objects. ``mnemonic`` picks the curve (any log
    type, #23); gamma is the default. Wells lacking logs or the curve are
    skipped, not fatal. Returns {title, image, curve, used, skipped}.
    """
    import matplotlib
    matplotlib.use("Agg")

    from ..welllog import curves as wl
    from ..welllog import plot as wlp

    tracks: dict = {}
    tops_by_label: dict = {}
    used: list[str] = []
    skipped: list[str] = []
    for well in wells:
        las_files = well.files.get("logs", [])
        if not las_files:
            skipped.append(well.well_id)
            continue
        try:
            df = wl.read_las(las_files[0])
            pick = mnemonic if (mnemonic and mnemonic in df.columns) else wl.gamma_column(df)
            label = f"{well.well_id}:{pick}"
            tracks[label] = wl.curve_series(df, pick)
            tops = _formation_tops(well.well_id)
            if tops:
                tops_by_label[label] = tops
            used.append(well.well_id)
        except Exception:
            skipped.append(well.well_id)

    if not tracks:
        raise ValueError(f"none of the selected wells have a {mnemonic or 'gamma'} curve")

    curve = mnemonic or "gamma"
    fig = wlp.plot_correlation(tracks, tops_by_label=tops_by_label)
    return {
        "title": f"{curve} across {len(used)} well(s)",
        "image": _figure_to_data_uri(fig),
        "curve": curve,
        "used": used,
        "skipped": skipped,
    }


def run(well, kind: str, mnemonic: str | None, instruction: str) -> dict:
    """Dispatch a workflow instruction on a source to an output artifact."""
    if kind == "log":
        return {"kind": "plot", **plot_log(well, mnemonic, instruction)}
    raise ValueError(f"unsupported source kind: {kind!r}")
