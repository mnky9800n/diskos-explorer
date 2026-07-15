"""Workflow runner tests (headless matplotlib via conftest)."""

from pathlib import Path

from diskos import wells
from diskos.web import workflow

SAMPLE_ROOT = Path(__file__).parent / "data" / "diskos_sample"


def test_plot_log_renders_gamma():
    well = wells.well_files(SAMPLE_ROOT, "7_11-1")
    out = workflow.plot_log(well)
    assert out["mnemonic"] == "GR"
    assert out["image"].startswith("data:image/png;base64,")
    assert "7_11-1" in out["title"]


def test_run_dispatches_log():
    well = wells.well_files(SAMPLE_ROOT, "7_11-1")
    out = workflow.run(well, "log", None, "plot the gamma log")
    assert out["kind"] == "plot"


def test_run_rejects_unknown_kind():
    well = wells.well_files(SAMPLE_ROOT, "7_11-1")
    try:
        workflow.run(well, "banana", None, "")
        assert False, "expected ValueError"
    except ValueError:
        pass
