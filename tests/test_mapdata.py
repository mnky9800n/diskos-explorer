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
