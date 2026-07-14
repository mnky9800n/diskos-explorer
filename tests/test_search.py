"""Local wiki search (BM25) tests."""

from diskos.wiki.search import search


def _make_wiki(tmp_path):
    entities = tmp_path / "entities"
    entities.mkdir()
    (entities / "well_a.md").write_text(
        "# Well A\nApectodinium homomorphum dominates this Balder section.\n", encoding="utf-8"
    )
    (entities / "well_b.md").write_text(
        "# Well B\nSpiniferites ramosus and Azolla in the Sele formation.\n", encoding="utf-8"
    )
    # Navigation files must be ignored by search.
    (tmp_path / "index.md").write_text("# Index\nApectodinium Apectodinium\n", encoding="utf-8")
    (tmp_path / "log.md").write_text("## [2026-07-14] ingest | well A\n", encoding="utf-8")
    return tmp_path


def test_search_ranks_relevant_page_first(tmp_path):
    wiki = _make_wiki(tmp_path)
    results = search(wiki, "Apectodinium homomorphum")
    assert results
    assert results[0]["path"].name == "well_a.md"


def test_search_skips_index_and_log(tmp_path):
    wiki = _make_wiki(tmp_path)
    results = search(wiki, "Apectodinium")
    names = {r["path"].name for r in results}
    assert "index.md" not in names
    assert "log.md" not in names


def test_search_returns_snippet(tmp_path):
    wiki = _make_wiki(tmp_path)
    results = search(wiki, "Azolla")
    assert results[0]["path"].name == "well_b.md"
    assert "Azolla" in results[0]["snippet"]


def test_search_no_match(tmp_path):
    wiki = _make_wiki(tmp_path)
    assert search(wiki, "tyrannosaurus") == []
