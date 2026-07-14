"""Borehole catalog tests against a real-structure fixture tree."""

from pathlib import Path

from diskos import wells

SAMPLE_ROOT = Path(__file__).parent / "data" / "diskos_sample"


def test_list_well_ids_excludes_admin():
    ids = wells.list_well_ids(SAMPLE_ROOT)
    assert ids == ["25_7-5", "35_9-1", "7_11-1"]
    assert "000-README" not in ids  # admin dir skipped


def test_well_files_buckets_by_type():
    assert wells.well_files(SAMPLE_ROOT, "7_11-1").counts() == {"logs": 1}
    assert wells.well_files(SAMPLE_ROOT, "35_9-1").counts() == {"geology": 1, "images": 1}
    assert wells.well_files(SAMPLE_ROOT, "25_7-5").counts() == {"geochem": 1}


def test_classify_real_patterns():
    # A LAS under LOGS is a petrophysical log; under WELL_PATH it is a survey.
    assert wells.classify("LOGS", "35_10-8_S_WLC_COMPOSITE_1.LAS") == "logs"
    assert wells.classify("WELL_PATH", "6603_12-1__LOGS__WELLPATH_COMPUTED__1.LAS") == "deviation"
    # .ASC here is Tigress (well path / checkshot), never StrataBugs palynology.
    assert wells.classify("WELL_PATH", "35_9-1__WELL_PATH__8109DEV.ASC") == "deviation"
    assert wells.classify("WELL_SEISMIC", "35_9-1__WELL_SEISMIC__8109CHKSHTMD.ASC") == "seismic"
    # Reports / geology PDFs; cuttings photos; QEMSCAN/XRF csv.
    assert wells.classify("GEOLOGY", "35_9-1__GEOLOGY__BIOSTRAT_REPORT_1.PDF") == "geology"
    assert wells.classify("DRILLING", "25_2-18_S_CUTTINGS_PHOTO_QEMSCAN_M_1.PNG") == "images"
    assert wells.classify("DRILLING", "25_2-18_S_CUTTINGS_QEMSCAN_RAW_1.CSV") == "geochem"


def test_is_biostrat():
    assert wells.is_biostrat(Path("35_9-1__GEOLOGY__BIOSTRAT_REPORT_1.PDF"))
    assert not wells.is_biostrat(Path("35_9-1__GEOLOGY__STRAT_REPORT_1.PDF"))


def test_catalog_recurses_all_wells():
    cat = wells.catalog(SAMPLE_ROOT)
    assert set(cat) == {"25_7-5", "35_9-1", "7_11-1"}
    assert cat["7_11-1"].has("logs")
