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
    fig = wlp.plot_correlation({f"{well.well_id}:{pick}": series})
    return {"title": f"{well.well_id}  {pick} vs depth", "image": _figure_to_data_uri(fig), "mnemonic": pick}


def run(well, kind: str, mnemonic: str | None, instruction: str) -> dict:
    """Dispatch a workflow instruction on a source to an output artifact."""
    if kind == "log":
        return {"kind": "plot", **plot_log(well, mnemonic, instruction)}
    raise ValueError(f"unsupported source kind: {kind!r}")
