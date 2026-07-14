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


def test_ask_endpoint_uses_model(client, monkeypatch):
    class FakeClient:
        def ask(self, prompt, **kwargs):
            return "The Jurassic sequence is dated by dinoflagellate cysts."

    monkeypatch.setattr("diskos.web.assistant.make_client", lambda: FakeClient())
    resp = client.post("/api/wells/35_9-1/ask", json={"question": "Summarize the biostrat"})
    assert resp.status_code == 200
    assert "Jurassic" in resp.json()["answer"]


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
