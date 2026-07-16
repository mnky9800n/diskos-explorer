"""Dossier assembly tests (deterministic, no model)."""

from pathlib import Path

from diskos import npd, wells
from diskos.boreholes import group_boreholes
from diskos.wiki.dossier import build_dossier

SAMPLE_ROOT = Path(__file__).parent / "data" / "diskos_sample"
NPD_SAMPLE = Path(__file__).parent / "data" / "npd_sample"


def _groups():
    records = npd.load_factpages(NPD_SAMPLE)
    return group_boreholes(wells.catalog(SAMPLE_ROOT), records)


def test_dossier_assembles_identity_location_and_logs():
    groups = _groups()
    d = build_dossier(groups["7_11-1"], all_groups=groups)

    assert d["borehole_id"] == "7_11-1"
    assert d["sidetracks"] == ["7_11-1_A"]
    assert d["location"]["field"] == "SLEIPNER"
    assert d["location"]["coord_source"] == "npd"
    assert d["npd"]["content"] == "GAS"

    # Both member LAS logs are present; gamma stats surfaced.
    assert d["inventory"].get("logs") == 2
    assert d["logs"] and d["logs"][0]["gamma"]["curve"] == "GR"
    # The duplicate seismic export was collapsed but counted.
    assert d["duplicate_count"] == 1


def test_dossier_reports_and_gaps():
    groups = _groups()
    # 35_9-1 has a biostrat report and no logs.
    d = build_dossier(groups["35_9-1"], all_groups=groups)
    assert any(r["biostrat"] for r in d["reports"])
    assert d["inventory"].get("logs") is None  # no logs -> honest gap
    assert d["palynology"] is None  # no per-well CSV supplied


def test_dossier_neighbors_by_distance():
    groups = _groups()
    d = build_dossier(groups["7_11-1"], all_groups=groups)
    ids = [n["borehole_id"] for n in d["neighbors"]]
    assert "7_11-1" not in ids  # never itself
    assert all("distance_km" in n for n in d["neighbors"])
