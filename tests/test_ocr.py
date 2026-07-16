"""OCR cache + dossier integration tests (offline; no model, no pymupdf)."""

from pathlib import Path

from diskos import npd, wells
from diskos.boreholes import group_boreholes
from diskos.io.ocr import cached_ocr, has_text_layer, ocr_cache_path
from diskos.wiki.dossier import build_dossier

SAMPLE_ROOT = Path(__file__).parent / "data" / "diskos_sample"
NPD_SAMPLE = Path(__file__).parent / "data" / "npd_sample"
BIOSTRAT = SAMPLE_ROOT / "35_9-1" / "GEOLOGY" / "35_9-1__GEOLOGY__BIOSTRAT_REPORT_1.PDF"


def test_cache_path_stable_and_read(tmp_path):
    p1 = ocr_cache_path(BIOSTRAT, tmp_path)
    p2 = ocr_cache_path(BIOSTRAT, tmp_path)
    assert p1 == p2
    assert cached_ocr(BIOSTRAT, tmp_path) is None  # nothing cached yet
    p1.write_text("Apectodinium acme at 2040 m\n", encoding="utf-8")
    assert "Apectodinium" in cached_ocr(BIOSTRAT, tmp_path)


def test_scanned_fixture_has_no_text_layer():
    assert has_text_layer(BIOSTRAT) is False


def test_dossier_picks_up_cached_ocr(tmp_path):
    # Seed an OCR transcript for the scanned biostrat report.
    ocr_cache_path(BIOSTRAT, tmp_path).parent.mkdir(parents=True, exist_ok=True)
    ocr_cache_path(BIOSTRAT, tmp_path).write_text(
        "Zonation summary: Apectodinium homomorphum acme 2037-2074 m.", encoding="utf-8"
    )
    groups = group_boreholes(wells.catalog(SAMPLE_ROOT), npd.load_factpages(NPD_SAMPLE))

    # Without OCR: the report reads as scanned/no-text.
    plain = build_dossier(groups["35_9-1"])
    assert plain["reports"][0]["has_text"] is False
    assert plain["reports"][0]["source"] == ""

    # With the OCR cache: text is recovered and marked as coming from OCR.
    enriched = build_dossier(groups["35_9-1"], ocr_dir=tmp_path)
    rep = enriched["reports"][0]
    assert rep["has_text"] is True
    assert rep["source"] == "ocr"
    assert "Apectodinium" in enriched["report_excerpt"]
