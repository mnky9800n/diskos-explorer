"""Well-log plots: gamma (and other curves) as depth-aligned color tracks.

Reproduces the intent of the notebook's welly ``plot_2d`` correlation panels (a
filled color strip with the curve overlaid, one column per well, aligned by
depth) using matplotlib directly, so it works on our pandas-3 stack.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def plot_log_track(series: pd.Series, ax=None, cmap: str = "viridis_r", label: str | None = None):
    """Plot one curve as a color-filled depth track with the line overlaid.

    Depth increases downward. Returns the Axes.
    """
    import matplotlib.pyplot as plt

    if ax is None:
        _, ax = plt.subplots(figsize=(2, 10))

    depth = series.index.to_numpy(dtype=float)
    values = series.to_numpy(dtype=float)

    # Color strip: extent puts shallow depth at the top (increasing downward).
    ax.imshow(
        values[:, None], aspect="auto", cmap=cmap,
        extent=[0, 1, float(np.nanmax(depth)), float(np.nanmin(depth))],
    )

    # Overlay the curve, normalized into the [0, 1] strip width.
    vmin, vmax = np.nanmin(values), np.nanmax(values)
    if vmax > vmin:
        xnorm = (values - vmin) / (vmax - vmin)
        ax.plot(xnorm, depth, color="k", lw=0.5)

    ax.set_xticks([])
    ax.set_ylabel("depth (m)")
    if label:
        ax.set_title(label, fontsize=10)
    return ax


def plot_correlation(tracks: dict[str, pd.Series], cmap: str = "viridis_r", out_path: str | Path | None = None):
    """Plot several wells' curves side by side, one column each, for correlation.

    ``tracks`` maps a label (well ID or curve name) to a depth-indexed Series.
    Returns the Figure.
    """
    import matplotlib.pyplot as plt

    n = len(tracks)
    if n == 0:
        raise ValueError("No tracks to plot.")

    fig, axes = plt.subplots(1, n, figsize=(2 * n, 10), squeeze=False)
    for ax, (label, series) in zip(axes[0], tracks.items()):
        plot_log_track(series, ax=ax, cmap=cmap, label=label)

    fig.tight_layout()
    if out_path is not None:
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
    return fig
