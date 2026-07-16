"""Wiki build tests: deterministic (no model) borehole + field pages."""

from pathlib import Path

from diskos.wiki.build import build_wiki
from diskos.wiki.dossier import build_dossier
from diskos.wiki.ingest import render_borehole_page

SAMPLE_ROOT = Path(__file__).parent / "data" / "diskos_sample"
NPD_SAMPLE = Path(__file__).parent / "data" / "npd_sample"


def test_build_writes_borehole_and_field_pages(tmp_path):
    summary = build_wiki(
        SAMPLE_ROOT, tmp_path, scope="all",
        well_client=None, field_client=None, npd_dir=NPD_SAMPLE,
    )
    # 7_11-1 + sidetrack collapse -> 3 boreholes.
    assert summary["boreholes"] == 3
    assert summary["pages_written"] == 3

    ent = tmp_path / "entities"
    assert (ent / "well_7_11-1.md").exists()
    assert (ent / "well_35_9-1.md").exists()
    # SLEIPNER field page and the fieldless block page both exist.
    assert (ent / "field_SLEIPNER.md").exists()
    assert (ent / "field_35_9.md").exists()

    page = (ent / "well_7_11-1.md").read_text()
    assert "type: borehole" in page
    assert "SLEIPNER field" in page
    assert "[[well_7_11-1_A]]" in page  # sidetrack link
    assert "## Gaps and confidence" in page
    assert "Absence reflects what is in the local mirror" in page

    # index.md and log.md were maintained.
    assert "Boreholes" in (tmp_path / "index.md").read_text()
    assert "borehole 7_11-1" in (tmp_path / "log.md").read_text()


def test_build_is_resumable(tmp_path):
    build_wiki(SAMPLE_ROOT, tmp_path, scope="all", npd_dir=NPD_SAMPLE)
    again = build_wiki(SAMPLE_ROOT, tmp_path, scope="all", npd_dir=NPD_SAMPLE)
    assert again["pages_written"] == 0
    assert again["pages_skipped"] == 3


def test_scope_single_field_block(tmp_path):
    summary = build_wiki(SAMPLE_ROOT, tmp_path, scope=("field", "35_9"), npd_dir=NPD_SAMPLE)
    assert summary["directories"] == 1  # only 35_9-1 is in block 35_9
    assert (tmp_path / "entities" / "well_35_9-1.md").exists()


def test_render_handles_empty_well():
    # A borehole with nothing but an ID renders honest gaps, not a crash.
    from diskos.boreholes import BoreholeGroup

    empty = BoreholeGroup(borehole_id="99_9-9")
    page = render_borehole_page(build_dossier(empty), on_date="2026-01-01")
    assert "No catalogued files in the mirror." in page
    assert "No report in the local mirror." in page
    assert "No coordinates resolved" in page
