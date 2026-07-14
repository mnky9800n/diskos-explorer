"""Borehole discovery tests: the catalog must generalize to any well."""

from pathlib import Path

from diskos import wells

SAMPLE_ROOT = Path(__file__).parent / "data" / "diskos_sample"


def test_catalog_discovers_well():
    cat = wells.catalog(SAMPLE_ROOT)
    assert "7_11-1" in cat
    assert len(cat["7_11-1"].paly) == 1
    assert cat["7_11-1"].paly[0].suffix == ".ASC"


def test_catalog_groups_paly_and_logs_under_one_well():
    # The .ASC (root) and the .LAS (7_11-1/LOGS/) share a derived well ID and
    # group together, even though they live in different places.
    cat = wells.catalog(SAMPLE_ROOT)
    well = cat["7_11-1"]
    assert len(well.logs) == 1
    assert well.logs[0].suffix == ".LAS"


def test_extract_well_id_generalizes_to_novel_ids():
    # None of these appear in Jack's notebooks; discovery must still work.
    assert wells.extract_well_id("16_2-3_R.ASC") == "16_2-3"
    assert wells.extract_well_id("6608_10-1__LOGS__COMPOSITE.LAS") == "6608_10-1"
    assert wells.extract_well_id("no_well_here.txt") is None


def test_classify_by_type():
    cat = wells.catalog(SAMPLE_ROOT)
    well = cat["7_11-1"]
    assert well.has("paly")
    assert well.has("logs")
    assert not well.has("xrf")
