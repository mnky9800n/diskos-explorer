"""FastAPI backend for the diskosAI web front end (scaffold).

Reuses the pipeline modules directly (io/palyno/wells), so the app is a thin API
over the same code the CLI uses. Every data endpoint is gated by the Google-OAuth
+ allowlist dependency in ``auth.py`` (dev-mode bypass for local work and tests).

Run with `diskos serve` (or uvicorn). The React/HTML front end is a later step;
this exposes the JSON the UI will consume.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

STATIC_DIR = Path(__file__).parent / "static"

from .. import wells as wells_mod
from ..config import load_config
from ..io.stratabugs import parse_stratabugs_simple
from ..palyno import reconcile
from ..palyno.aggregate import create_wide_format
from ..palyno.targets import TARGETS
from ..paths import diskos_root
from .auth import current_user, dev_mode


def _records(wide: pd.DataFrame) -> list[dict]:
    """Wide depth-indexed frame -> JSON-safe list of row dicts (NaN -> null)."""
    frame = wide.reset_index()
    frame = frame.astype(object).where(pd.notna(frame), None)
    return frame.to_dict(orient="records")


def _downsample(index, values, max_points: int = 1500):
    """Evenly thin two parallel sequences to at most ``max_points`` pairs."""
    n = len(index)
    if n <= max_points:
        step = 1
    else:
        step = int(np.ceil(n / max_points))
    return list(index[::step]), list(values[::step])


def _well_or_404(well_id: str):
    root = diskos_root(load_config())
    catalog = wells_mod.catalog(root)
    if well_id not in catalog:
        raise HTTPException(status_code=404, detail=f"Well {well_id} not found.")
    return catalog[well_id]


def _well_logs(well_id: str, mnemonic: str | None) -> list[dict]:
    from ..welllog import curves as wl

    files = []
    for las in _well_or_404(well_id).logs:
        df = wl.read_las(las)
        mnems = wl.available_mnemonics(df)
        gamma = None
        try:
            gamma = wl.gamma_column(df)
        except KeyError:
            pass
        pick = mnemonic if (mnemonic and mnemonic in df.columns) else (gamma or (mnems[0] if mnems else None))
        tracks = []
        if pick:
            series = df[pick].dropna()
            depths, values = _downsample(list(series.index), [float(v) for v in series.to_numpy()])
            tracks.append({
                "mnemonic": pick,
                "points": [{"depth": float(d), "value": float(v)} for d, v in zip(depths, values)],
            })
        files.append({"file": las.name, "mnemonics": mnems, "gamma": gamma, "tracks": tracks})
    return files


def _well_xrf(well_id: str, depth: int | None, range_type: str) -> list[dict]:
    from ..xrf import fit as xrf

    files = []
    for csv in _well_or_404(well_id).xrf:
        df = xrf.read_niton_csv(csv)
        depths, ranges = xrf.depths_and_ranges(df)
        rt = range_type if range_type in ranges else (ranges[0] if ranges else "")
        d = depth if depth in depths else (depths[0] if depths else None)
        spectrum = None
        label = f"{d}m ({rt})"
        if d is not None and label in df.index:
            energy = xrf.energy_axis(df)
            counts = df.loc[label].to_numpy(dtype=float)
            e, c = _downsample(list(energy), list(counts), max_points=1200)
            spectrum = {"depth": d, "range": rt, "energy": [float(x) for x in e], "counts": [float(x) for x in c]}
        files.append({"file": csv.name, "depths": depths, "ranges": ranges, "spectrum": spectrum})
    return files


def _well_palynology(well_id: str) -> list[dict]:
    cfg = load_config()
    root = diskos_root(cfg)
    catalog = wells_mod.catalog(root)
    if well_id not in catalog:
        raise HTTPException(status_code=404, detail=f"Well {well_id} not found.")
    decisions = reconcile.Decisions.load(cfg.decisions_path())

    files = []
    for asc in catalog[well_id].paly:
        obs = parse_stratabugs_simple(asc)["observations"]
        if obs.empty:
            continue
        available = sorted(obs["taxon_name"].dropna().unique().tolist())
        result = reconcile.resolve_matches(TARGETS, available, decisions)
        wide = create_wide_format(obs, result.mapping)
        files.append(
            {
                "file": asc.name,
                "columns": list(wide.columns),
                "records": _records(wide),
                "pending_decisions": [
                    {"target": p.target, "variant": p.variant, "similarity": p.similarity}
                    for p in result.pending
                ],
            }
        )
    return files


def create_app() -> FastAPI:
    app = FastAPI(title="diskosAI", version="0.1.0")
    app.add_middleware(
        SessionMiddleware,
        secret_key=os.environ.get("DISKOS_SESSION_SECRET", "dev-insecure-secret"),
    )
    _register_oauth(app)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "dev_mode": dev_mode()}

    @app.get("/api/me")
    def me(user: str = Depends(current_user)) -> dict:
        return {"email": user, "dev_mode": dev_mode()}

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/wells")
    def list_wells(user: str = Depends(current_user)) -> list[dict]:
        root = diskos_root(load_config())
        catalog = wells_mod.catalog(root)
        return [
            {
                "well_id": wid,
                "paly": len(w.paly),
                "logs": len(w.logs),
                "xrf": len(w.xrf),
            }
            for wid, w in sorted(catalog.items())
        ]

    @app.get("/api/wells/{well_id}")
    def well_detail(well_id: str, user: str = Depends(current_user)) -> dict:
        root = diskos_root(load_config())
        catalog = wells_mod.catalog(root)
        if well_id not in catalog:
            raise HTTPException(status_code=404, detail=f"Well {well_id} not found.")
        w = catalog[well_id]
        return {
            "well_id": well_id,
            "paly": [p.name for p in w.paly],
            "logs": [p.name for p in w.logs],
            "xrf": [p.name for p in w.xrf],
        }

    @app.get("/api/wells/{well_id}/palynology")
    def well_palynology(well_id: str, user: str = Depends(current_user)) -> dict:
        return {"well_id": well_id, "files": _well_palynology(well_id)}

    @app.get("/api/wells/{well_id}/logs")
    def well_logs(well_id: str, mnemonic: str = None, user: str = Depends(current_user)) -> dict:
        return {"well_id": well_id, "files": _well_logs(well_id, mnemonic)}

    @app.get("/api/wells/{well_id}/xrf")
    def well_xrf(
        well_id: str,
        depth: int = None,
        range_type: str = "Main Range",
        user: str = Depends(current_user),
    ) -> dict:
        return {"well_id": well_id, "files": _well_xrf(well_id, depth, range_type)}

    # Static assets (styles, script). Mounted last so it never shadows /api routes.
    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    return app


def _register_oauth(app: FastAPI) -> None:
    """Register Google OIDC routes if credentials are present, else stub /auth/login.

    Real login needs GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET. Without them the app
    still runs (use dev mode); login just reports that OAuth is not configured.
    """
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")

    if not (client_id and client_secret):
        @app.get("/auth/login")
        def login_unconfigured() -> dict:
            return {
                "detail": "Google OAuth not configured. Set GOOGLE_CLIENT_ID / "
                "GOOGLE_CLIENT_SECRET, or run with DISKOS_WEB_DEV=1."
            }
        return

    from authlib.integrations.starlette_client import OAuth
    from fastapi import Request
    from fastapi.responses import RedirectResponse

    oauth = OAuth()
    oauth.register(
        name="google",
        client_id=client_id,
        client_secret=client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

    @app.get("/auth/login")
    async def login(request: Request):
        redirect_uri = request.url_for("auth_callback")
        return await oauth.google.authorize_redirect(request, redirect_uri)

    @app.get("/auth/callback", name="auth_callback")
    async def auth_callback(request: Request):
        from .auth import is_allowed

        token = await oauth.google.authorize_access_token(request)
        userinfo = token.get("userinfo") or {}
        email = userinfo.get("email")
        if not is_allowed(email):
            raise HTTPException(status_code=403, detail=f"{email} is not allowlisted.")
        request.session["user"] = email
        return RedirectResponse(url="/")

    @app.get("/auth/logout")
    async def logout(request: Request):
        request.session.pop("user", None)
        return RedirectResponse(url="/")


# Module-level app for `uvicorn diskos.web.api:app`.
app = create_app()
