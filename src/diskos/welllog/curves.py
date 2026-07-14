"""Read and slice well-log curves from LAS files.

Ported from Jack's ``Well_Logs.ipynb``, which was fully inline with hardcoded
per-well LAS paths and depth intervals. Here paths come from the borehole catalog
and intervals are optional arguments, so the same code runs on any well.

The notebook used ``welly``, but welly 0.5.2 is incompatible with pandas 3 (its
curve resampling calls the removed ``Index.is_numeric()``). We read LAS with
``lasio`` (welly's own reader, lightweight and pandas-3 clean) into a depth-indexed
DataFrame and do slicing / blocking with pandas + numpy, which we control.

Gamma (GR/HGR/...) is the primary curve for lithology and for the gamma-vs-core
calibration Jack described; other downhole curves are read the same way.
"""

from __future__ import annotations

from pathlib import Path

import lasio
import numpy as np
import pandas as pd

# Common gamma-ray mnemonics, in preference order. Operators differ.
GAMMA_MNEMONICS = ("GR", "HGR", "CGR", "SGR", "GRD", "GRR")


def read_las(las_path: str | Path) -> pd.DataFrame:
    """Load a LAS file into a depth-indexed DataFrame (one column per curve)."""
    df = lasio.read(str(las_path)).df()
    if df.index.name is None:
        df.index.name = "DEPT"
    return df


def available_mnemonics(df: pd.DataFrame) -> list[str]:
    """Curve mnemonics present in the well."""
    return list(df.columns)


def gamma_column(df: pd.DataFrame) -> str:
    """Return the name of the gamma curve, trying the common mnemonics in order."""
    for mnemonic in GAMMA_MNEMONICS:
        if mnemonic in df.columns:
            return mnemonic
    raise KeyError(
        f"No gamma curve found (tried {GAMMA_MNEMONICS}). "
        f"Available: {available_mnemonics(df)}"
    )


def curve_series(df: pd.DataFrame, mnemonic: str) -> pd.Series:
    """Return one curve by mnemonic, or raise listing what exists."""
    if mnemonic not in df.columns:
        raise KeyError(
            f"Curve {mnemonic!r} not in well. Available: {available_mnemonics(df)}"
        )
    return df[mnemonic]


def slice_depth(obj: pd.DataFrame | pd.Series, top: float | None = None, bottom: float | None = None):
    """Restrict a depth-indexed frame/series to an interval (full range if unbounded)."""
    if top is None and bottom is None:
        return obj
    lo = top if top is not None else obj.index.min()
    hi = bottom if bottom is not None else obj.index.max()
    return obj[(obj.index >= lo) & (obj.index <= hi)]


def block_series(series: pd.Series, cutoffs, values=None) -> pd.Series:
    """Discretize a curve into blocks by value cutoffs (e.g. a GR sand/shale cutoff).

    ``cutoffs`` is a scalar or ascending list of edges. Without ``values`` each
    sample gets its bin index (0..len(cutoffs)); with ``values`` each bin maps to
    the given representative value. Reproduces the intent of welly's ``block``.
    """
    edges = [cutoffs] if np.isscalar(cutoffs) else list(cutoffs)
    bins = np.digitize(series.to_numpy(dtype=float), edges)
    if values is not None:
        mapped = np.array([values[min(i, len(values) - 1)] for i in bins], dtype=float)
    else:
        mapped = bins.astype(float)
    return pd.Series(mapped, index=series.index, name=f"{series.name}_block")
