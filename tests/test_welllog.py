"""Well-log (LAS) module tests, using lasio + a minimal LAS fixture."""

from pathlib import Path

from diskos.welllog import curves, plot

LAS = (
    Path(__file__).parent
    / "data" / "diskos_sample" / "7_11-1" / "LOGS" / "7_11-1__LOGS__COMPOSITE__1.LAS"
)


def test_read_las_and_gamma_column():
    df = curves.read_las(LAS)
    assert "GR" in curves.available_mnemonics(df)
    assert curves.gamma_column(df) == "GR"
    assert df.shape[0] == 10


def test_slice_depth():
    df = curves.read_las(LAS)
    gr = curves.curve_series(df, "GR")
    sub = curves.slice_depth(gr, 1002, 1006)
    assert sub.index.min() == 1002.0
    assert sub.index.max() == 1006.0
    assert len(sub) == 5


def test_block_series_by_cutoff():
    df = curves.read_las(LAS)
    gr = curves.curve_series(df, "GR")
    # Below 75 -> bin 0 (sand-like), at/above -> bin 1 (shale-like).
    blocked = curves.block_series(gr, cutoffs=75)
    assert blocked.loc[1000.0] == 0  # GR 45
    assert blocked.loc[1002.0] == 1  # GR 95
    # With representative values.
    mapped = curves.block_series(gr, cutoffs=75, values=[10.0, 90.0])
    assert mapped.loc[1000.0] == 10.0
    assert mapped.loc[1002.0] == 90.0


def test_plot_correlation_writes_figure(tmp_path):
    df = curves.read_las(LAS)
    gr = curves.curve_series(df, "GR")
    out = tmp_path / "logs.png"
    plot.plot_correlation({"7_11-1:GR": gr}, out_path=out)
    assert out.exists() and out.stat().st_size > 0


def test_track_fill_is_clipped_behind_curve():
    # The gradient image must be clipped (to the region left of the curve), not
    # flooding the whole track (issue #21).
    import matplotlib
    matplotlib.use("Agg")

    df = curves.read_las(LAS)
    ax = plot.plot_log_track(curves.curve_series(df, "GR"))
    images = ax.get_images()
    assert images, "expected a gradient image"
    assert images[0].get_clip_path() is not None  # clipped, not full-track
