"""NPD/Sodir FactPages load + match tests (offline fixture CSV)."""

from pathlib import Path

from diskos import npd

NPD_SAMPLE = Path(__file__).parent / "data" / "npd_sample"


def test_normalize_name():
    assert npd.normalize_name("34/8-14 A") == "34_8-14_A"
    assert npd.normalize_name("1/3-A-1 H") == "1_3-A-1_H"
    assert npd.normalize_name("1/2-1") == "1_2-1"


def test_load_and_match():
    records = npd.load_factpages(NPD_SAMPLE)
    assert len(records) == 4

    rec = npd.match(records, "7_11-1")
    assert rec is not None
    assert rec.field == "SLEIPNER"
    assert abs(rec.lat - 58.371) < 1e-6
    assert abs(rec.lon - 1.905) < 1e-6
    assert rec.npdid == "101"

    # A sidetrack points at the same parent well.
    st = npd.match(records, "7_11-1_A")
    assert st is not None
    assert st.well == "7/11-1"


def test_match_absent_and_zero_coords():
    records = npd.load_factpages(NPD_SAMPLE)
    assert npd.match(records, "ADDA-1") is None
    # A dry well with no field still resolves, field is None not "".
    dry = npd.match(records, "35_9-1")
    assert dry is not None and dry.field is None


def test_load_missing_dir_is_empty():
    assert npd.load_factpages(Path("/no/such/npd/dir")) == {}
