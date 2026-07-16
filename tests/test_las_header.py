"""LAS header extraction tests."""

from pathlib import Path

from diskos.io.las import read_las_header

SAMPLE_ROOT = Path(__file__).parent / "data" / "diskos_sample"
LAS = SAMPLE_ROOT / "7_11-1" / "LOGS" / "7_11-1__LOGS__COMPOSITE__1.LAS"


def test_read_las_header_surfaces_identity_and_location():
    header = read_las_header(LAS)
    assert header["well"] == "7/11-1 S"
    assert header["field"] == "TESTFIELD"
    assert "56 30" in header["lat_dms"]
    assert "003 12" in header["lon_dms"]


def test_read_las_header_missing_file_is_empty():
    assert read_las_header(SAMPLE_ROOT / "nope.LAS") == {}
