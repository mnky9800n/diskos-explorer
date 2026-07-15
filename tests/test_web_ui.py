"""Web UI serving tests: the SPA shell, static assets, and /api/me."""

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


def test_index_served(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "DISKOS Explorer" in resp.text
    assert "static/app.js" in resp.text


def test_static_assets_served(client):
    for path, needle in [("/static/app.js", "renderFilesPanel"), ("/static/styles.css", "depthchart")]:
        resp = client.get(path)
        assert resp.status_code == 200, path
        assert needle in resp.text


def test_index_default_base(client):
    assert '<base href="/"' in client.get("/").text


def test_index_injects_subpath_base(monkeypatch):
    monkeypatch.setenv("DISKOS_WEB_DEV", "1")
    monkeypatch.setenv("DISKOS_ROOT", str(SAMPLE_ROOT))
    monkeypatch.setenv("DISKOS_BASE_PATH", "/diskos-explorer/")
    from diskos.web.api import create_app

    assert '<base href="/diskos-explorer/"' in TestClient(create_app()).get("/").text


def test_api_me_dev(client):
    resp = client.get("/api/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "dev@local"
    assert body["dev_mode"] is True
