"""Report/data provenance graph tests."""

from pathlib import Path

from diskos import wells
from diskos.web import graph

SAMPLE_ROOT = Path(__file__).parent / "data" / "diskos_sample"


def test_report_interval():
    assert graph.report_interval("studied 2037.5m - 2274.8m of section") == [2037.5, 2274.8]
    assert graph.report_interval("intervals 2100-2200 m and 2400-2500m") == [2100.0, 2500.0]
    assert graph.report_interval("no depths mentioned") is None


def test_overlaps():
    assert graph._overlaps([2000, 2300], [1500, 2100])
    assert not graph._overlaps([2000, 2300], [100, 500])


def test_build_well_graph_has_report_node():
    g = graph.build_well_graph(wells.well_files(SAMPLE_ROOT, "35_9-1"))
    assert g["well_id"] == "35_9-1"
    kinds = [n["kind"] for n in g["nodes"]]
    assert "report" in kinds
    # the fixture PDF is a stub with no text, so no interval and no edges
    assert g["edges"] == []
