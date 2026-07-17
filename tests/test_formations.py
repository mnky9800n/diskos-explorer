"""SODIR formation-tops load + lookup, and the plot overlay (#22)."""

from pathlib import Path

from diskos import formations

NPD_SAMPLE = Path(__file__).parent / "data" / "npd_sample"
SAMPLE_ROOT = Path(__file__).parent / "data" / "diskos_sample"
LAS = SAMPLE_ROOT / "7_11-1" / "LOGS" / "7_11-1__LOGS__COMPOSITE__1.LAS"


def test_load_and_lookup():
    tops = formations.load_formation_tops(NPD_SAMPLE)
    assert "7_11-1" in tops
    # ordered by depth, both levels present
    names = [t.name for t in tops["7_11-1"]]
    assert names[0] == "NORDLAND GP"
    assert "BALDER FM" in names


def test_tops_for_filters_by_level():
    tops = formations.load_formation_tops(NPD_SAMPLE)
    fms = formations.tops_for(tops, "7_11-1", level="FORMATION")
    assert [t.name for t in fms] == ["BALDER FM", "SELE FM"]
    assert all(t.level == "FORMATION" for t in fms)


def test_tops_for_missing_well_is_empty():
    tops = formations.load_formation_tops(NPD_SAMPLE)
    assert formations.tops_for(tops, "99_9-9") == []


def test_load_missing_table_is_empty(tmp_path):
    assert formations.load_formation_tops(tmp_path) == {}


def test_plot_overlays_formation_labels():
    import matplotlib
    matplotlib.use("Agg")

    from diskos.welllog import curves, plot

    tops = formations.tops_for(formations.load_formation_tops(NPD_SAMPLE), "7_11-1", level="FORMATION")
    ax = plot.plot_log_track(curves.curve_series(curves.read_las(LAS), "GR"), tops=tops)
    labels = [t.get_text() for t in ax.texts]
    assert "BALDER FM" in labels and "SELE FM" in labels
