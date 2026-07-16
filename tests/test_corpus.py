"""Corpus index tests: coverage, quadrant parsing, finder."""

from pathlib import Path

from diskos.web import corpus

SAMPLE_ROOT = Path(__file__).parent / "data" / "diskos_sample"


def test_parse_quadrant_block():
    assert corpus.parse_quadrant_block("35_9-1") == ("35", "9")
    assert corpus.parse_quadrant_block("6603_12-1") == ("6603", "12")
    assert corpus.parse_quadrant_block("ADDA-1") == (None, None)


def test_build_index_and_stats():
    idx = corpus.build_index(SAMPLE_ROOT, refresh=True)
    by_id = {e["well_id"]: e for e in idx}
    assert by_id["7_11-1"]["types"] == ["logs"]
    assert by_id["35_9-1"]["biostrat"] is True
    assert by_id["35_9-1"]["quadrant"] == "35"

    s = corpus.stats(idx)
    assert s["n_wells"] == 4  # 7_11-1 plus its sidetrack 7_11-1_A
    assert s["biostrat"] == 1
    assert s["coverage"].get("logs") == 2
    assert s["coverage"].get("geology") == 1


def test_find():
    idx = corpus.build_index(SAMPLE_ROOT, refresh=True)
    assert [e["well_id"] for e in corpus.find(idx, data_type="logs")] == ["7_11-1", "7_11-1_A"]
    assert [e["well_id"] for e in corpus.find(idx, biostrat=True)] == ["35_9-1"]
    assert [e["well_id"] for e in corpus.find(idx, quadrant="35")] == ["35_9-1"]
