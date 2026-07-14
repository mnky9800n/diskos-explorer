"""Palynology plots: species (count or abundance) versus depth.

Rebuilt from Jack's ``Palynology_Plot.ipynb``. The notebook's plotting code was
incomplete ("not really working yet") and its three near-duplicate variants are
collapsed here into one parameterized function. The footgun is removed: nothing
writes back to the source CSVs. ``apectodinium_sum`` returns a Series in memory
instead of overwriting files.

Consumes the per-well CSVs produced by the stratabugs pipeline (depth index with
``<Species>_cnt`` / ``_abn`` / ``_p-out`` columns). Formation shading from a tops
spreadsheet is optional.
"""

from __future__ import annotations

import math
import os
import re
from pathlib import Path

import pandas as pd

# Qualitative abundance codes mapped to plottable magnitudes (from the notebook).
ABUND_MAP = {"P": 1, "R": 2, "C": 5, "A": 15, "D": 50}

_WELL_KEY_RE = re.compile(r"(\d+_\d+-\d+(?:_\w)?)")


def palyno_well_key_from_fname(fname: str) -> str:
    """Derive a well key (e.g. ``35_10-8_S``) from a CSV file name."""
    stem = os.path.splitext(os.path.basename(fname))[0]
    match = _WELL_KEY_RE.match(stem)
    return match.group(1) if match else stem


def count_columns(df: pd.DataFrame) -> list[str]:
    """Species count columns present in a per-well CSV."""
    return [c for c in df.columns if c.endswith("_cnt")]


def numeric_series(df: pd.DataFrame, col: str) -> pd.Series:
    """Return a plottable numeric series for a species column.

    Count columns are used as-is; abundance / presence columns (``_abn`` /
    ``_p-out``) have their qualitative codes mapped via ABUND_MAP.
    """
    if col.endswith("_cnt"):
        return pd.to_numeric(df[col], errors="coerce")
    return df[col].map(ABUND_MAP)


def apectodinium_sum(df: pd.DataFrame) -> pd.Series:
    """Row-wise sum of all Apectodinium count columns (NaN if all NaN).

    Returned in memory; unlike the notebook, this never writes to the CSV.
    """
    cols = [c for c in df.columns if c.startswith("Apectodinium_") and c.endswith("_cnt")]
    numeric = df[cols].apply(pd.to_numeric, errors="coerce")
    return numeric.sum(axis=1, min_count=1)


def load_formation_tops(
    path: str | Path,
    wlb_col: str = "Wellbore name",
    top_col: str = "Top depth [m]",
    bot_col: str = "Bottom depth [m]",
    unit_col: str = "Lithostrat. unit",
) -> pd.DataFrame:
    """Load a formation-tops spreadsheet and normalize well names to keys.

    Returns a DataFrame with columns: well_key, top, bottom, unit.
    """
    units = pd.read_excel(path)
    out = pd.DataFrame(
        {
            "well_key": units[wlb_col].astype(str).str.strip().str.replace("/", "_", regex=False).str.replace(" ", "_", regex=False),
            "top": pd.to_numeric(units[top_col], errors="coerce"),
            "bottom": pd.to_numeric(units[bot_col], errors="coerce"),
            "unit": units[unit_col].astype(str),
        }
    )
    return out


def plot_species_vs_depth(
    df: pd.DataFrame,
    species_cols: list[str] | None = None,
    depth_col: str = "depth",
    ax=None,
    colors: dict[str, str] | None = None,
    tops: pd.DataFrame | None = None,
    well_key: str | None = None,
    formation_colors: dict[str, str] | None = None,
    title: str | None = None,
):
    """Plot one well: chosen species versus depth (depth increasing downward).

    Returns the matplotlib Axes. Formation intervals from ``tops`` (filtered to
    ``well_key``) are drawn as shaded horizontal bands when provided.
    """
    import matplotlib.pyplot as plt

    if ax is None:
        _, ax = plt.subplots(figsize=(6, 10))
    if species_cols is None:
        species_cols = count_columns(df)
    colors = colors or {}

    depths = pd.to_numeric(df[depth_col], errors="coerce")
    for col in species_cols:
        if col not in df.columns:
            continue
        values = numeric_series(df, col)
        mask = values.notna() & depths.notna()
        if not mask.any():
            continue
        ax.plot(
            values[mask], depths[mask], marker="o", markersize=5, linewidth=1,
            color=colors.get(col, None), label=col,
        )

    if tops is not None and well_key is not None:
        fcolors = formation_colors or {}
        for _, row in tops[tops["well_key"] == well_key].iterrows():
            if pd.isna(row["top"]) or pd.isna(row["bottom"]):
                continue
            ax.axhspan(
                row["top"], row["bottom"], color=fcolors.get(row["unit"], "lightgrey"),
                alpha=0.25, zorder=0, label=row["unit"],
            )

    if not ax.yaxis_inverted():
        ax.invert_yaxis()
    ax.set_xlabel("count / abundance")
    ax.set_ylabel(depth_col)
    if title:
        ax.set_title(title)
    return ax


def plot_wells(
    frames: dict[str, pd.DataFrame],
    species_cols: list[str] | None = None,
    depth_col: str = "depth",
    colors: dict[str, str] | None = None,
    tops: pd.DataFrame | None = None,
    formation_colors: dict[str, str] | None = None,
    out_path: str | Path | None = None,
):
    """Plot a grid of wells (one subplot each) and optionally save to a file.

    ``frames`` maps a label (e.g. file name or well key) to its per-well
    DataFrame. Returns the matplotlib Figure.
    """
    import matplotlib.pyplot as plt

    n = len(frames)
    if n == 0:
        raise ValueError("No wells to plot.")

    ncols = math.ceil(math.sqrt(n))
    nrows = math.ceil(n / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(6 * ncols, 10 * nrows), squeeze=False)
    flat = axes.flatten()

    for ax, (label, df) in zip(flat, frames.items()):
        plot_species_vs_depth(
            df, species_cols=species_cols, depth_col=depth_col, ax=ax, colors=colors,
            tops=tops, well_key=palyno_well_key_from_fname(label),
            formation_colors=formation_colors, title=label,
        )
        handles, labels = ax.get_legend_handles_labels()
        if handles:
            ax.legend(fontsize=7)

    for ax in flat[n:]:
        ax.set_visible(False)

    fig.tight_layout()
    if out_path is not None:
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
    return fig
