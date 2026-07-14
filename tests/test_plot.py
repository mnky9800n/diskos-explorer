"""Palynology plotting tests (headless Agg backend via conftest)."""

from pathlib import Path

import pandas as pd

from diskos.palyno import plot as palyno_plot


def _sample_df():
    return pd.DataFrame(
        {
            "depth": [1000.0, 1050.0, 1100.0],
            "Apectodinium_homomorphum_cnt": [7, 5, None],
            "Apectodinium_augustum_cnt": [1, None, 3],
            "Azolla_abn": ["R", "C", None],
        }
    )


def test_count_columns_and_numeric_mapping():
    df = _sample_df()
    assert set(palyno_plot.count_columns(df)) == {
        "Apectodinium_homomorphum_cnt",
        "Apectodinium_augustum_cnt",
    }
    # Abundance codes map through ABUND_MAP; counts pass through.
    assert palyno_plot.numeric_series(df, "Azolla_abn").tolist()[:2] == [2, 5]
    assert palyno_plot.numeric_series(df, "Apectodinium_homomorphum_cnt").tolist()[0] == 7


def test_apectodinium_sum_in_memory():
    df = _sample_df()
    result = palyno_plot.apectodinium_sum(df)
    # 7 + 1 at depth 1000; source frame is untouched.
    assert result.iloc[0] == 8
    assert "Apectodinium_sum" not in df.columns


def test_well_key_from_fname():
    assert palyno_plot.palyno_well_key_from_fname("35_10-8_S.csv") == "35_10-8_S"
    assert palyno_plot.palyno_well_key_from_fname("7_11-1.csv") == "7_11-1"


def test_plot_wells_writes_figure(tmp_path):
    out = tmp_path / "fig.png"
    palyno_plot.plot_wells({"7_11-1_S.csv": _sample_df()}, out_path=out)
    assert out.exists() and out.stat().st_size > 0


def test_formation_tops_roundtrip_and_shading(tmp_path):
    tops_xlsx = tmp_path / "tops.xlsx"
    pd.DataFrame(
        {
            "Wellbore name": ["7/11-1 S"],
            "Top depth [m]": [1020.0],
            "Bottom depth [m]": [1080.0],
            "Lithostrat. unit": ["BALDER FM"],
        }
    ).to_excel(tops_xlsx, index=False)

    tops = palyno_plot.load_formation_tops(tops_xlsx)
    assert tops.loc[0, "well_key"] == "7_11-1_S"

    out = tmp_path / "fig.png"
    palyno_plot.plot_wells({"7_11-1_S.csv": _sample_df()}, tops=tops, out_path=out)
    assert out.exists() and out.stat().st_size > 0
