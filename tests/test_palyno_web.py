"""Palynology upload -> species-vs-depth plot -> CSV export (Batch D, #5/#9)."""

from pathlib import Path

from fastapi.testclient import TestClient

SAMPLE_ROOT = Path(__file__).parent / "data" / "diskos_sample"
ASC = Path(__file__).parent / "data" / "curated_paly" / "7_11-1_S.ASC"


def _client(monkeypatch, tmp_path):
    monkeypatch.setenv("DISKOS_WEB_DEV", "1")
    monkeypatch.setenv("DISKOS_ROOT", str(SAMPLE_ROOT))
    monkeypatch.setenv("DISKOS_PALYNO_DIR", str(tmp_path))
    monkeypatch.delenv("DISKOS_ALLOWLIST", raising=False)
    from diskos.web.api import create_app

    return TestClient(create_app())


def test_palyno_upload_plot_csv(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)

    with open(ASC, "rb") as fh:
        r = c.post("/api/palyno/upload", files={"file": ("7_11-1_S.ASC", fh, "text/plain")})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["well"] == "7_11-1_S"
    assert "Apectodinium_homomorphum" in d["species"]
    assert d["depths"] >= 1

    plot = c.get("/api/palyno/7_11-1_S/plot", params={"species": "Apectodinium_homomorphum"}).json()
    assert plot["image"].startswith("data:image/png;base64,")

    csv = c.get("/api/palyno/7_11-1_S/csv")
    assert csv.status_code == 200
    assert "depth" in csv.text.splitlines()[0]


def test_palyno_plot_404_when_not_uploaded(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    assert c.get("/api/palyno/nope/plot").status_code == 404
