"""Well-log plots: gamma (and other curves) as depth-aligned color tracks.

Reproduces the intent of the notebook's welly ``plot_2d`` correlation panels (a
filled color strip with the curve overlaid, one column per well, aligned by
depth) using matplotlib directly, so it works on our pandas-3 stack.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def plot_log_track(series: pd.Series, ax=None, cmap: str = "viridis_r", label: str | None = None, tops=None):
    """Plot one curve as a depth track with a gradient filled behind the curve.

    The color gradient (by value) fills only the area between the left axis and
    the curve, not the whole track, so the curve's shape reads clearly (matching
    Jack's notebook). Depth increases downward. If ``tops`` (a list of
    FormationTop) is given, formation boundaries are drawn across the track with
    the unit name labelled down the depth axis (#22). Returns the Axes.
    """
    import matplotlib.pyplot as plt
    from matplotlib.patches import PathPatch
    from matplotlib.path import Path as MplPath

    if ax is None:
        _, ax = plt.subplots(figsize=(2, 10))

    depth = series.index.to_numpy(dtype=float)
    values = series.to_numpy(dtype=float)
    top, bot = float(np.nanmin(depth)), float(np.nanmax(depth))

    vmin, vmax = np.nanmin(values), np.nanmax(values)
    xnorm = (values - vmin) / (vmax - vmin) if vmax > vmin else np.zeros_like(values)

    # Gradient colored by value at each depth, spanning the track width...
    im = ax.imshow(values[:, None], aspect="auto", cmap=cmap, extent=[0, 1, bot, top])

    # ...then clipped to the region left of the curve, so the fill sits behind
    # the curve instead of flooding the whole track.
    finite = np.isfinite(xnorm) & np.isfinite(depth)
    xf, df = xnorm[finite], depth[finite]
    if xf.size >= 2:
        verts = np.column_stack([xf, df]).tolist() + [[0.0, df[-1]], [0.0, df[0]]]
        clip = PathPatch(MplPath(verts), transform=ax.transData, facecolor="none", edgecolor="none")
        ax.add_patch(clip)
        im.set_clip_path(clip)
        ax.plot(xf, df, color="k", lw=0.6)

    ax.set_xlim(0, 1)
    ax.set_ylim(bot, top)  # shallow at top, deep at bottom
    ax.set_xticks([])
    ax.set_ylabel("depth (m)")

    if tops:
        _draw_formation_tops(ax, tops, top, bot)

    if label:
        ax.set_title(label, fontsize=10)
    return ax


def _draw_formation_tops(ax, tops, top: float, bot: float) -> None:
    """Draw formation boundaries as horizontal lines with names down the axis."""
    for unit in tops:
        depth = unit.top
        if depth is None or not (top <= depth <= bot):
            continue
        ax.axhline(depth, color="0.35", lw=0.6)
        # Label in the (white) area right of the curve; clip long names to the track.
        ax.text(
            0.97, depth + (bot - top) * 0.004, unit.name,
            fontsize=6, va="top", ha="right", color="0.15", clip_on=True,
        )


def plot_correlation(tracks: dict[str, pd.Series], cmap: str = "viridis_r", out_path: str | Path | None = None, tops_by_label: dict | None = None):
    """Plot several wells' curves side by side, one column each, for correlation.

    ``tracks`` maps a label (well ID or curve name) to a depth-indexed Series.
    ``tops_by_label`` optionally maps the same label to that well's formation
    tops, drawn on its track. Returns the Figure.
    """
    import matplotlib.pyplot as plt

    n = len(tracks)
    if n == 0:
        raise ValueError("No tracks to plot.")

    tops_by_label = tops_by_label or {}
    fig, axes = plt.subplots(1, n, figsize=(2 * n, 10), squeeze=False)
    for ax, (label, series) in zip(axes[0], tracks.items()):
        plot_log_track(series, ax=ax, cmap=cmap, label=label, tops=tops_by_label.get(label))

    fig.tight_layout()
    if out_path is not None:
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
    return fig
