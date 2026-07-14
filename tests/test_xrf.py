"""XRF tests: CSV/config/area helpers (PyMca fit path is skipped if unavailable)."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from diskos.xrf import fit

CSV = (
    Path(__file__).parent
    / "data" / "diskos_sample" / "25_7-5" / "25_7-5_CUTTINGS_XRF_RAW_1.CSV"
)


def test_read_niton_csv_and_axis():
    df = fit.read_niton_csv(CSV)
    assert df.shape == (4, 5)
    assert fit.energy_axis(df).tolist() == [0.0, 0.015, 0.03, 0.045, 0.06]
    calib = fit.calibration(df)
    assert calib["zero"] == 0.0
    assert round(calib["gain"], 3) == 0.015


def test_parse_sample_id_and_grouping():
    assert fit.parse_sample_id("1350m (Main Range)") == (1350, "Main Range")
    assert fit.parse_sample_id("weird") == (None, "weird")
    df = fit.read_niton_csv(CSV)
    depths, ranges = fit.depths_and_ranges(df)
    assert depths == [1350, 1400]
    assert ranges == ["Low Range", "Main Range"]


def test_stack_for_range():
    df = fit.read_niton_csv(CSV)
    rows, stack, sum_spectrum, depths = fit.stack_for_range(df, "Main Range")
    assert stack.shape == (2, 5)
    assert depths == [1350, 1400]
    assert sum_spectrum.tolist() == (stack[0] + stack[1]).tolist()


def test_default_config_fixes_matrix_and_has_peaks():
    cfg = fit.default_fit_config_dict()
    # Fixed from the notebook's biased pure-Si matrix.
    assert cfg["attenuators"]["Matrix"][1] == "SiO2"
    assert len(cfg["peaks"]) == 9
    assert cfg["concentrations"]["usematrix"] == 1


def test_areas_and_proportions_math():
    areas = np.array([[10.0, 20.0], [30.0, 10.0]])  # (n_elements=2, n_depths=2)
    df = fit.areas_to_dataframe(areas, ["Fe K", "Ca K"], [1350, 1400])
    assert df.loc[1350, "Fe K"] == 10.0
    props = fit.proportions(df)
    # Row 1350: Fe 10, Ca 30 -> 0.25 / 0.75.
    assert round(props.loc[1350, "Fe K"], 3) == 0.25
    assert round(props.loc[1350, "Ca K"], 3) == 0.75


def test_fit_spectra_requires_pymca():
    pytest.importorskip("PyMca5", reason="PyMca5 has no wheel for this Python; verify on lambda-scalar")
    df = fit.read_niton_csv(CSV)
    cfg_path = CSV.parent / "my_config.cfg"
    fit.write_config(fit.default_fit_config_dict(), cfg_path)
    result = fit.fit_spectra(df, cfg_path, "Main Range")
    assert "areas_df" in result
