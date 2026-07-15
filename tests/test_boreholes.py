"""Identity resolution, grouping, dedup, and location tests."""

from pathlib import Path

from diskos import npd, wells
from diskos.boreholes import borehole_id, dedupe, group_boreholes, quadrant_block

SAMPLE_ROOT = Path(__file__).parent / "data" / "diskos_sample"
NPD_SAMPLE = Path(__file__).parent / "data" / "npd_sample"


def test_borehole_id_heuristic_without_npd():
    assert borehole_id("34_8-14_A") == "34_8-14"
    assert borehole_id("1_3-11_T2") == "1_3-11"
    assert borehole_id("35_10-8_S") == "35_10-8"
    # Platform and base wells are untouched.
    assert borehole_id("34_7-P-44") == "34_7-P-44"
    assert borehole_id("10_4-1") == "10_4-1"
    assert borehole_id("ADDA-1") == "ADDA-1"


def test_borehole_id_authoritative_with_npd():
    records = npd.load_factpages(NPD_SAMPLE)
    # NPD says 7/11-1 A's parent well is 7/11-1.
    assert borehole_id("7_11-1_A", records) == "7_11-1"


def test_quadrant_block():
    assert quadrant_block("31_2-1") == ("31", "31_2")
    assert quadrant_block("1_3-10") == ("1", "1_3")
    assert quadrant_block("ADDA-1") == (None, None)


def test_dedupe_flags_byte_identical():
    seismic = wells.well_files(SAMPLE_ROOT, "7_11-1_A").files["seismic"]
    assert len(seismic) == 2  # two names, same bytes
    unique, dups = dedupe(seismic)
    assert len(unique) == 1
    assert len(dups) == 1


def test_group_collapses_sidetrack_with_npd():
    records = npd.load_factpages(NPD_SAMPLE)
    catalog = wells.catalog(SAMPLE_ROOT)
    groups = group_boreholes(catalog, records)

    # 7_11-1 and its sidetrack 7_11-1_A collapse to one borehole.
    assert "7_11-1" in groups
    group = groups["7_11-1"]
    assert set(group.well_ids) == {"7_11-1", "7_11-1_A"}
    assert group.sidetracks == ["7_11-1_A"]
    # Location resolved authoritatively from NPD.
    assert group.coord_source == "npd"
    assert group.field_name == "SLEIPNER"
    assert abs(group.lat - 58.371) < 1e-6
    # Merged seismic bucket is deduped (2 raw files -> 1 unique + 1 dup pair).
    assert len(group.files.get("seismic", [])) == 1
    assert len(group.duplicate_pairs) == 1


def test_group_without_npd_falls_back_to_las_header():
    catalog = wells.catalog(SAMPLE_ROOT)
    groups = group_boreholes(catalog, records=None)
    # Heuristic still collapses the sidetrack.
    assert set(groups["7_11-1"].well_ids) == {"7_11-1", "7_11-1_A"}
    # Location comes from the LAS header (TESTFIELD, 56 30' N / 003 12' E).
    group = groups["7_11-1"]
    assert group.coord_source == "las"
    assert group.field_name == "TESTFIELD"
    assert abs(group.lat - 56.5) < 1e-3
    assert abs(group.lon - 3.2) < 1e-3
