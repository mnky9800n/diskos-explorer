"""Well-assistant tests: report extraction + prompt, with an injected model."""

from pathlib import Path

from diskos import wells
from diskos.web import assistant

SAMPLE_ROOT = Path(__file__).parent / "data" / "diskos_sample"


class FakeClient:
    def __init__(self):
        self.prompt = None

    def ask(self, prompt, **kwargs):
        self.prompt = prompt
        return "Canned answer grounded in the report."


def test_build_prompt_includes_inventory_and_context():
    p = assistant.build_prompt("35_9-1", "- logs (1): a.LAS", "excerpt text here", "What ages?")
    assert "35_9-1" in p
    assert "What ages?" in p
    assert "excerpt text here" in p
    assert "a.LAS" in p  # data inventory reaches the model


def test_format_inventory_lists_types():
    well = wells.well_files(SAMPLE_ROOT, "35_9-1")
    inv = assistant.format_inventory(well)
    assert "geology" in inv and "images" in inv


def test_extract_report_text_notes_scans(tmp_path):
    # A stub PDF with no text layer is reported as a scan, not counted as a source.
    f = tmp_path / "W__GEOLOGY__BIOSTRAT_REPORT_1.PDF"
    f.write_text("%PDF-1.4\n")
    text, used = assistant.extract_report_text([f])
    assert used == []
    assert "no extractable text" in text


def test_biostrat_ordered_first(tmp_path):
    a = tmp_path / "W__GEOLOGY__STRAT_REPORT.PDF"
    b = tmp_path / "W__GEOLOGY__BIOSTRAT_REPORT.PDF"
    a.write_text("x"); b.write_text("x")
    assert assistant._biostrat_first([a, b])[0].name == b.name


def test_answer_question_with_injected_client():
    well = wells.well_files(SAMPLE_ROOT, "35_9-1")
    fake = FakeClient()
    result = assistant.answer_question(well, "Summarize the biostratigraphy.", client=fake)
    assert result["answer"] == "Canned answer grounded in the report."
    assert "35_9-1" in fake.prompt  # well id passed into the prompt
    assert any("BIOSTRAT" in name for name in result["reports_available"])
