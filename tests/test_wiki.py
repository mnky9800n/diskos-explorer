"""Wiki ingest tests: deterministic (no model), plus optional injected client."""

from pathlib import Path

import pandas as pd

from diskos.wiki import ingest
from diskos.wiki.index import append_log, upsert_index_entry


def _write_csv(path: Path):
    pd.DataFrame(
        {
            "depth": [1000.0, 1050.0],
            "Apectodinium_homomorphum_cnt": [7, 5],
            "Azolla_cnt": [None, 1],
        }
    ).to_csv(path, index=False)


def test_summarize_well_csv(tmp_path):
    csv = tmp_path / "7_11-1_S.csv"
    _write_csv(csv)
    summary = ingest.summarize_well_csv(csv)
    assert summary["n_depths"] == 2
    assert summary["depth_min"] == 1000.0 and summary["depth_max"] == 1050.0
    assert summary["totals"]["Apectodinium_homomorphum"] == 12
    assert summary["totals"]["Azolla"] == 1


def test_ingest_writes_page_index_and_log(tmp_path):
    csv = tmp_path / "7_11-1_S.csv"
    _write_csv(csv)
    wiki = tmp_path / "wiki"
    (wiki).mkdir()
    (wiki / "index.md").write_text("# Wiki Index\n\n## Entities\n", encoding="utf-8")

    page = ingest.ingest_well_csv(csv, wiki, on_date="2026-07-14")
    assert page.exists()
    text = page.read_text()
    assert "# Well 7_11-1_S" in text
    assert "[[Apectodinium homomorphum]]" in text
    assert "—" not in text  # house rule: no em dashes

    index = (wiki / "index.md").read_text()
    assert "entities/well_7_11-1_S.md" in index
    log = (wiki / "log.md").read_text()
    assert log.startswith("## [2026-07-14] ingest | well 7_11-1_S")


def test_ingest_is_idempotent_in_index(tmp_path):
    csv = tmp_path / "7_11-1_S.csv"
    _write_csv(csv)
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "index.md").write_text("# Wiki Index\n\n## Entities\n", encoding="utf-8")

    ingest.ingest_well_csv(csv, wiki, on_date="2026-07-14")
    ingest.ingest_well_csv(csv, wiki, on_date="2026-07-15")
    index = (wiki / "index.md").read_text()
    # One catalog line for the well, not two.
    assert index.count("entities/well_7_11-1_S.md") == 1
    # But the log has both ingests (append-only).
    assert (wiki / "log.md").read_text().count("ingest | well 7_11-1_S") == 2


def test_ingest_with_injected_model_adds_prose(tmp_path):
    csv = tmp_path / "7_11-1_S.csv"
    _write_csv(csv)
    wiki = tmp_path / "wiki"
    wiki.mkdir()

    class FakeClient:
        def ask(self, prompt, **kwargs):
            return "Apectodinium dominates the section."

    page = ingest.ingest_well_csv(csv, wiki, on_date="2026-07-14", client=FakeClient())
    assert "Apectodinium dominates the section." in page.read_text()


def test_upsert_replaces_and_log_appends(tmp_path):
    wiki = tmp_path
    (wiki / "index.md").write_text("# Wiki Index\n\n## Entities\n", encoding="utf-8")
    upsert_index_entry(wiki, "Entities", "entities/a.md", "well A", "old")
    upsert_index_entry(wiki, "Entities", "entities/a.md", "well A", "new")
    index = (wiki / "index.md").read_text()
    assert "new" in index and "old" not in index
    append_log(wiki, "2026-07-14", "ingest", "x")
    append_log(wiki, "2026-07-14", "lint", "y")
    assert (wiki / "log.md").read_text().count("## [2026-07-14]") == 2
