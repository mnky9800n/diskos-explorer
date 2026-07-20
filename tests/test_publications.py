"""Crossref publications: parsing + endpoint (mocked, no network)."""

from pathlib import Path

from fastapi.testclient import TestClient

from diskos import publications

SAMPLE_ROOT = Path(__file__).parent / "data" / "diskos_sample"


def test_parse_crossref_items():
    data = {"message": {"items": [{
        "title": ["A study of well 31/2-1"],
        "author": [{"family": "Smith", "given": "J"}, {"family": "Lee"}],
        "published": {"date-parts": [[2005, 3]]},
        "DOI": "10.1/x", "URL": "https://doi.org/10.1/x",
        "container-title": ["J. Pet. Geol."],
    }]}}
    out = publications._parse(data)
    assert out[0]["title"].startswith("A study")
    assert out[0]["authors"] == "Smith, Lee"
    assert out[0]["year"] == 2005
    assert out[0]["doi"] == "10.1/x"


def test_parse_skips_untitled():
    assert publications._parse({"message": {"items": [{"DOI": "x"}]}}) == []


def test_publications_endpoint(monkeypatch, tmp_path):
    monkeypatch.setenv("DISKOS_WEB_DEV", "1")
    monkeypatch.setenv("DISKOS_ROOT", str(SAMPLE_ROOT))
    monkeypatch.delenv("DISKOS_ALLOWLIST", raising=False)
    monkeypatch.setattr(
        publications, "search",
        lambda q, **k: [{"title": f"Paper about {q}", "authors": "A", "year": 2010,
                         "doi": f"10/{q}", "url": "u", "container": "C"}],
    )
    from diskos.web import api

    api._PUBS_CACHE.clear()
    c = TestClient(api.create_app())
    d = c.get("/api/wells/7_11-1/publications").json()
    assert d["well"] == "7_11-1"
    assert d["publications"] and d["publications"][0]["title"].startswith("Paper about")
