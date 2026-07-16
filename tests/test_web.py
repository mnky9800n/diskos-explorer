"""Web API tests via FastAPI TestClient, in dev-auth mode (no real OAuth)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SAMPLE_ROOT = Path(__file__).parent / "data" / "diskos_sample"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DISKOS_WEB_DEV", "1")
    monkeypatch.setenv("DISKOS_ROOT", str(SAMPLE_ROOT))
    monkeypatch.delenv("DISKOS_ALLOWLIST", raising=False)
    from diskos.web.api import create_app

    return TestClient(create_app())


def test_health_is_open(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_list_wells_requires_dev_user_and_returns_catalog(client):
    resp = client.get("/api/wells")
    assert resp.status_code == 200
    ids = [w["well_id"] for w in resp.json()]
    assert "7_11-1" in ids


def test_well_detail_categorized(client):
    resp = client.get("/api/wells/35_9-1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["counts"] == {"geology": 1, "images": 1}
    assert body["biostrat"] == ["35_9-1__GEOLOGY__BIOSTRAT_REPORT_1.PDF"]


def test_unknown_well_404(client):
    assert client.get("/api/wells/99_99-9").status_code == 404


def test_corpus_stats_endpoint(client):
    d = client.get("/api/corpus").json()
    assert d["n_wells"] == 4
    assert d["biostrat"] == 1
    assert d["coverage"].get("logs") == 2


def test_corpus_find_endpoint(client):
    d = client.get("/api/corpus/find", params={"biostrat": "true"}).json()
    assert d["count"] == 1
    assert d["wells"][0]["well_id"] == "35_9-1"


def test_corpus_ask_endpoint(client, monkeypatch):
    class FakeClient:
        def ask(self, prompt, **kwargs):
            return "About a third of the archive has biostratigraphy reports."

    monkeypatch.setattr("diskos.web.assistant.make_client", lambda: FakeClient())
    r = client.post("/api/corpus/ask", json={"question": "how much has biostrat?"})
    assert r.status_code == 200
    assert "biostrat" in r.json()["answer"]


def test_detail_files_carry_rel_paths(client):
    files = client.get("/api/wells/35_9-1").json()["files"]
    geo = files["geology"][0]
    assert geo["name"].endswith(".PDF")
    assert geo["rel"].startswith("GEOLOGY/")


def test_file_serving(client):
    resp = client.get(
        "/api/wells/35_9-1/file",
        params={"path": "GEOLOGY/35_9-1__GEOLOGY__BIOSTRAT_REPORT_1.PDF"},
    )
    assert resp.status_code == 200
    assert resp.content.startswith(b"%PDF")


def test_file_serving_blocks_traversal(client):
    resp = client.get("/api/wells/35_9-1/file", params={"path": "../../etc/passwd"})
    assert resp.status_code == 403


def test_file_serving_404_for_missing(client):
    resp = client.get("/api/wells/35_9-1/file", params={"path": "GEOLOGY/nope.pdf"})
    assert resp.status_code == 404


def test_ask_endpoint_uses_model(client, monkeypatch):
    class FakeClient:
        def ask(self, prompt, **kwargs):
            return "The Jurassic sequence is dated by dinoflagellate cysts."

    monkeypatch.setattr("diskos.web.assistant.make_client", lambda: FakeClient())
    resp = client.post("/api/wells/35_9-1/ask", json={"question": "Summarize the biostrat"})
    assert resp.status_code == 200
    assert "Jurassic" in resp.json()["answer"]


def test_workflow_run_produces_plot(client):
    r = client.post("/api/workflow/run", json={"well_id": "7_11-1", "kind": "log", "instruction": "plot gamma"})
    assert r.status_code == 200
    d = r.json()
    assert d["kind"] == "plot"
    assert d["image"].startswith("data:image/png;base64,")


def test_graph_endpoint(client):
    g = client.get("/api/wells/35_9-1/graph").json()
    assert g["well_id"] == "35_9-1"
    assert any(n["kind"] == "report" for n in g["nodes"])


def test_logs_endpoint_returns_gamma_track(client):
    resp = client.get("/api/wells/7_11-1/logs")
    assert resp.status_code == 200
    files = resp.json()["files"]
    assert files and files[0]["gamma"] == "GR"
    track = files[0]["tracks"][0]
    assert track["mnemonic"] == "GR"
    assert track["points"] and "depth" in track["points"][0] and "value" in track["points"][0]


def test_allowlist_blocks_non_listed_user(monkeypatch):
    # Dev mode on, but a non-empty allowlist that excludes the default dev user.
    monkeypatch.setenv("DISKOS_WEB_DEV", "1")
    monkeypatch.setenv("DISKOS_ROOT", str(SAMPLE_ROOT))
    monkeypatch.setenv("DISKOS_ALLOWLIST", "someone@else.com")
    from diskos.web.api import create_app

    c = TestClient(create_app())
    assert c.get("/api/wells").status_code == 403
    # An allowlisted user (via dev header) gets through.
    ok = c.get("/api/wells", headers={"X-Dev-User": "someone@else.com"})
    assert ok.status_code == 200


def test_wiki_endpoints_serve_built_pages(monkeypatch, tmp_path):
    from diskos.wiki.build import build_wiki

    NPD_SAMPLE = Path(__file__).parent / "data" / "npd_sample"
    build_wiki(SAMPLE_ROOT, tmp_path, scope="all", npd_dir=NPD_SAMPLE)

    monkeypatch.setenv("DISKOS_WEB_DEV", "1")
    monkeypatch.setenv("DISKOS_ROOT", str(SAMPLE_ROOT))
    monkeypatch.setenv("DISKOS_WIKI_DIR", str(tmp_path))
    monkeypatch.delenv("DISKOS_ALLOWLIST", raising=False)
    from diskos.web.api import create_app

    c = TestClient(create_app())

    # A borehole page (sidetrack resolves to the parent's page).
    w = c.get("/api/wells/7_11-1_A/wiki").json()
    assert w["borehole_id"] == "7_11-1"
    assert w["exists"] is True
    assert "# Borehole 7_11-1" in w["markdown"]

    # A field page.
    f = c.get("/api/fields/SLEIPNER/wiki").json()
    assert f["exists"] is True
    assert "SLEIPNER" in f["markdown"]

    # BM25 search over the built pages.
    s = c.get("/api/wiki/search", params={"q": "gamma logs"}).json()
    assert s["results"]
    assert any("well_" in r["path"] for r in s["results"])

    # A borehole with no page yet degrades gracefully, not a 500.
    missing = c.get("/api/wells/99_9-9/wiki").json()
    assert missing["exists"] is False


def test_oauth_login_does_not_treat_request_as_query_param(monkeypatch):
    # Regression: `from __future__ import annotations` stringizes type hints, so
    # FastAPI resolves `request: Request` against module globals. When Request was
    # imported only inside _register_oauth, the string didn't resolve and FastAPI
    # treated `request` as a required query param -> 422 on /auth/login.
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "dummy-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "dummy-secret")
    monkeypatch.setenv("DISKOS_ROOT", str(SAMPLE_ROOT))
    from fastapi.routing import APIRoute

    from diskos.web.api import create_app

    app = create_app()
    login = next(
        r for r in app.routes if isinstance(r, APIRoute) and r.path == "/auth/login"
    )
    # The framework recognized `request` as the Request object, not a query field.
    assert [q.name for q in login.dependant.query_params] == []
