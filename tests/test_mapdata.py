"""Map-point extraction from built wiki pages."""

from pathlib import Path

from diskos.wiki.build import build_wiki
from diskos.wiki.mapdata import map_points

SAMPLE_ROOT = Path(__file__).parent / "data" / "diskos_sample"
NPD_SAMPLE = Path(__file__).parent / "data" / "npd_sample"


def test_map_points_reads_located_boreholes(tmp_path):
    build_wiki(SAMPLE_ROOT, tmp_path, scope="all", npd_dir=NPD_SAMPLE)
    points = map_points(tmp_path)

    by_id = {p["borehole_id"]: p for p in points}
    assert "7_11-1" in by_id
    p = by_id["7_11-1"]
    assert abs(p["lat"] - 58.371) < 1e-6
    assert abs(p["lon"] - 1.905) < 1e-6
    assert p["field"] == "SLEIPNER"
    assert p["coord_source"] == "npd"
    assert p["has_logs"] is True

    # 35_9-1 has the biostrat report flag set.
    assert by_id["35_9-1"]["biostrat"] is True


def test_map_points_empty_when_no_wiki(tmp_path):
    assert map_points(tmp_path) == []


def test_map_points_drops_garbage_coordinates(tmp_path):
    # A page written before the coordinate guard, with a UTM/null outlier, must
    # not appear on the map (one outlier would blow up the map's bounds).
    entities = tmp_path / "entities"
    entities.mkdir(parents=True)
    (entities / "well_good.md").write_text(
        "---\ntype: borehole\nborehole_id: 7_11-1\nlat: 58.3\nlon: 1.9\n---\n# ok\n"
    )
    (entities / "well_bad.md").write_text(
        "---\ntype: borehole\nborehole_id: 99_9-9\nlat: 6738756.98\nlon: 494437.07\n---\n# junk\n"
    )
    ids = [p["borehole_id"] for p in map_points(tmp_path)]
    assert ids == ["7_11-1"]
