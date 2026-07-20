"""Formation inverse index + NPD year parsing (Batch B)."""

from pathlib import Path

from diskos import formations, npd

NPD_SAMPLE = Path(__file__).parent / "data" / "npd_sample"


def test_wells_by_formation():
    tops = formations.load_formation_tops(NPD_SAMPLE)
    inv = formations.wells_by_formation(tops)
    assert inv["BALDER FM"] == {"7_11-1"}
    assert "NORDLAND GP" in inv


def test_all_formations_counts_and_level():
    tops = formations.load_formation_tops(NPD_SAMPLE)
    fms = {f["name"]: f for f in formations.all_formations(tops)}
    assert fms["BALDER FM"]["level"] == "FORMATION"
    assert fms["NORDLAND GP"]["level"] == "GROUP"
    assert fms["BALDER FM"]["count"] == 1
    # level filter
    only_fm = formations.all_formations(tops, level="FORMATION")
    assert all(f["level"] == "FORMATION" for f in only_fm)


def test_npd_parses_entry_year():
    recs = npd.load_factpages(NPD_SAMPLE)
    assert npd.match(recs, "7_11-1").year == 1989
    assert npd.match(recs, "25_7-5").year == 1978
