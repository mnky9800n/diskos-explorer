"""XRF (Niton handheld) spectrum reading and PyMca fitting.

Ported from Jack's WIP ``XRF-Analysis-PyMCA.ipynb``. Two fixes over the notebook:

1. Weight-percent extraction. The notebook called
   ``FastXRFLinearFit.fitDeriveMassFractions()`` / ``_fitDeriveMassFractions()``,
   which does not exist and raised AttributeError. The correct path is to pass
   ``concentrations=True`` to ``fitMultipleSpectra`` and read
   ``result["concentrations"]`` (+ ``result.labels("concentrations")``).
2. Matrix. The notebook used a pure-Si matrix (``["Si", ...]``) with usematrix=1,
   which biases fundamental-parameter concentrations for rock cuttings. The
   default here is ``SiO2`` (a generic rock/soil matrix); pass ``matrix=`` to
   override.

STATUS: the fitting path is UNVERIFIED. PyMca5 has no wheels for this Python and
we have no real Niton data here, so only the CSV/config/area helpers below are
tested. Verify the fit on lambda-scalar with PyMca5 installed and real spectra.
The flux/time/area/distance in the concentrations block are Niton-typical
placeholders and must be calibrated before wt% values are trusted.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

# Elements to fit and their line families (from the notebook).
DEFAULT_PEAKS = {
    "Si": ["K"], "S": ["K"], "Ca": ["K"], "Fe": ["K"], "Ti": ["K"],
    "Mn": ["K"], "Zn": ["K"], "Sr": ["K"], "Ba": ["L"],
}


def read_niton_csv(path: str | Path) -> pd.DataFrame:
    """Read a Niton raw-spectra CSV into a DataFrame (rows=samples, cols=energy).

    The first 4 rows are instrument metadata. The header row's columns are energy
    values (keV) as strings; the index is a sample id like ``"1350m (Main Range)"``.
    """
    df = pd.read_csv(path, skiprows=4, index_col=0, encoding="latin-1")
    df.index = df.index.astype(str).str.replace("\xa0", " ", regex=False).str.strip()
    return df


def energy_axis(df: pd.DataFrame) -> np.ndarray:
    """Energy (keV) per channel, from the column labels."""
    return df.columns.astype(float).to_numpy()


def calibration(df: pd.DataFrame) -> dict:
    """Return zero (keV), gain (keV/channel), and the channel index array."""
    energy = energy_axis(df)
    return {
        "zero": float(energy[0]),
        "gain": float(energy[1] - energy[0]),
        "channels": np.arange(len(energy)),
    }


def parse_sample_id(sid: str) -> tuple[int | None, str]:
    """Extract (depth_m, range_type) from a sample id like ``"1350m (Main Range)"``."""
    match = re.match(r"(\d+)m \((.+)\)", str(sid).strip())
    if match:
        return int(match.group(1)), match.group(2)
    return None, str(sid)


def depths_and_ranges(df: pd.DataFrame) -> tuple[list[int], list[str]]:
    parsed = [parse_sample_id(s) for s in df.index]
    depths = sorted({d for d, _ in parsed if d is not None})
    ranges = sorted({r for _, r in parsed})
    return depths, ranges


def stack_for_range(df: pd.DataFrame, range_type: str = "Main Range"):
    """Return (rows, stack, sum_spectrum, depths) for one Niton beam range."""
    rows = [s for s in df.index if range_type in s]
    stack = df.loc[rows].to_numpy(dtype=float)
    sum_spectrum = stack.sum(axis=0)
    depths = [parse_sample_id(s)[0] for s in rows]
    return rows, stack, sum_spectrum, depths


def default_fit_config_dict(matrix: str = "SiO2", xmin: int = 27, xmax: int = 3583) -> dict:
    """Build the PyMca fit configuration as a plain dict.

    ``matrix`` defaults to SiO2 (generic rock) rather than the notebook's pure Si.
    """
    return {
        "detector": {
            "zero": 0.0, "gain": 0.015, "noise": 0.1, "fano": 0.114, "sum": 1e-8,
            "detele": "Si", "detene": 1.7420, "ethreshold": 0.020,
            "ithreshold": 1.0e-07, "nthreshold": 4,
            "deltazero": 0.1, "deltagain": 0.001, "deltanoise": 0.05,
            "deltafano": 0.114, "deltasum": 1e-8,
            "fixedzero": 0, "fixedgain": 0, "fixednoise": 0, "fixedfano": 0, "fixedsum": 0,
        },
        "fit": {
            "energy": [50.0, 0.0, 0.0, 0.0], "energyweight": [1.0, 0.0, 0.0, 0.0],
            "energyflag": [1, 0, 0, 0], "energyscatter": [1, 0, 0, 0],
            "xmin": xmin, "xmax": xmax, "use_limit": 0,
            "continuum": 1, "stripiterations": 20000, "snipwidth": 30,
            "stripflag": 0, "stripanchorsflag": 0, "stripanchorslist": [0, 0, 0, 0],
            "fitfunction": 0, "hypermetflag": 1, "escapeflag": 1, "sumflag": 0,
            "scatterflag": 0, "linpolorder": 5, "exppolorder": 6, "linearfitflag": 0,
            "maxiter": 50, "deltachi": 1e-05, "deltaonepeak": 0.010, "fitweight": 1,
        },
        "peaks": dict(DEFAULT_PEAKS),
        "concentrations": {
            "usematrix": 1, "useattenuators": 1, "flux": 1e10, "time": 1.0,
            "area": 30.0, "distance": 10.0, "reference": "Auto",
        },
        "attenuators": {
            # [flag, material, density, thickness, alphain, alphaout]
            "Matrix": [1, matrix, 2.65, 0.0, 90.0, 90.0],
        },
    }


def write_config(config: dict, path: str | Path) -> Path:
    """Write a fit-config dict to a PyMca .cfg file (needs PyMca5)."""
    from PyMca5.PyMcaIO import ConfigDict

    cfg = ConfigDict.ConfigDict()
    cfg.update(config)
    cfg.write(str(path))
    return Path(path)


def areas_to_dataframe(element_areas: np.ndarray, labels: list[str], depths: list[int]) -> pd.DataFrame:
    """Net-area matrix (n_elements x n_depths) -> DataFrame indexed by depth."""
    df = pd.DataFrame(np.asarray(element_areas).T, index=depths, columns=labels)
    df.index.name = "Depth_m"
    return df


def proportions(areas_df: pd.DataFrame) -> pd.DataFrame:
    """Row-normalized proportions (each depth sums to 1)."""
    return areas_df.div(areas_df.sum(axis=1), axis=0)


def fit_spectra(df: pd.DataFrame, config_path: str | Path, range_type: str = "Main Range") -> dict:
    """Fit all spectra of one range with PyMca and return areas + concentrations.

    UNVERIFIED (see module docstring). Returns a dict with areas_df,
    proportions_df, and concentrations_df (wt%, via the fixed API path).
    """
    from PyMca5.PyMcaPhysics.xrf import FastXRFLinearFit

    calib = calibration(df)
    _, stack, sum_spectrum, depths = stack_for_range(df, range_type)

    fitter = FastXRFLinearFit.FastXRFLinearFit()
    fitter.setFitConfigurationFile(str(config_path))
    result = fitter.fitMultipleSpectra(
        x=calib["channels"], y=stack, ysum=sum_spectrum, concentrations=True
    )

    area_labels = result.labels("parameters")
    areas_df = areas_to_dataframe(result["parameters"], area_labels, depths)

    out = {"areas_df": areas_df, "proportions_df": proportions(areas_df)}

    # FIXED weight-percent path: read the concentrations buffer directly.
    if "concentrations" in list(result.keys()):
        conc_labels = result.labels("concentrations")
        out["concentrations_df"] = pd.DataFrame(
            np.asarray(result["concentrations"]).T, index=depths, columns=conc_labels
        )
    return out
