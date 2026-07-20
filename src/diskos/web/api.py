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
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

STATIC_DIR = Path(__file__).parent / "static"


def base_path() -> str:
    """URL prefix the app is served under (default '/'), trailing slash."""
    b = os.environ.get("DISKOS_BASE_PATH", "/")
    return b if b.endswith("/") else b + "/"


def wiki_dir() -> Path:
    """Directory holding the built wiki markdown (DISKOS_WIKI_DIR, default 'wiki')."""
    return Path(os.environ.get("DISKOS_WIKI_DIR", "wiki"))


_NPD_CACHE: dict[str, dict] = {}
_MAP_CACHE: dict[str, list] = {}
_TOPS_CACHE: dict[str, tuple] = {}


def _tops_and_records():
    """Cached (formation tops, wellbore register) for the analysis endpoint."""
    from ..config import load_config as _lc
    from .. import formations as _fm
    from .. import npd as _npd

    path = str(_lc().npd_path())
    if path not in _TOPS_CACHE:
        _TOPS_CACHE[path] = (_fm.load_formation_tops(path), _npd.load_factpages(path))
    return _TOPS_CACHE[path]


def _npd_records():
    """Cached Sodir/NPD register, to resolve a well_id to its borehole page."""
    from ..config import load_config as _lc
    from .. import npd as _npd

    path = str(_lc().npd_path())
    if path not in _NPD_CACHE:
        _NPD_CACHE[path] = _npd.load_factpages(path)
    return _NPD_CACHE[path]

from pydantic import BaseModel

from .. import wells as wells_mod
from ..config import load_config
from ..paths import diskos_root
from .auth import current_user, dev_mode


class AskBody(BaseModel):
    question: str


class WorkflowBody(BaseModel):
    well_id: str
    kind: str = "log"
    mnemonic: str | None = None
    instruction: str = ""


def _downsample(index, values, max_points: int = 1500):
    """Evenly thin two parallel sequences to at most ``max_points`` pairs."""
    n = len(index)
    step = 1 if n <= max_points else int(np.ceil(n / max_points))
    return list(index[::step]), list(values[::step])


def _well_or_404(well_id: str):
    """Resolve one well's categorized files, or 404. Recurses only that well."""
    root = diskos_root(load_config())
    if well_id not in wells_mod.list_well_ids(root):
        raise HTTPException(status_code=404, detail=f"Well {well_id} not found.")
    return wells_mod.well_files(root, well_id)


def _well_logs(well_id: str, mnemonic: str | None) -> list[dict]:
    from ..welllog import curves as wl

    files = []
    for las in _well_or_404(well_id).files.get("logs", []):
        try:
            df = wl.read_las(las)
        except Exception:
            continue  # unreadable / non-LAS content; skip rather than 500
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


def create_app() -> FastAPI:
    app = FastAPI(title="diskosAI", version="0.1.0")
    app.add_middleware(
        SessionMiddleware,
        secret_key=os.environ.get("DISKOS_SESSION_SECRET", "dev-insecure-secret"),
        same_site="lax",
        https_only=os.environ.get("DISKOS_COOKIE_SECURE", "0") == "1",
        domain=os.environ.get("DISKOS_COOKIE_DOMAIN") or None,  # e.g. .johnspace.xyz
    )
    # CORS so the Pages front-end (different subdomain) can call the API with the cookie.
    cors_origins = os.environ.get("DISKOS_CORS_ORIGIN")
    if cors_origins:
        from fastapi.middleware.cors import CORSMiddleware

        app.add_middleware(
            CORSMiddleware,
            allow_origins=[o.strip() for o in cors_origins.split(",") if o.strip()],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    _register_oauth(app)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "dev_mode": dev_mode()}

    @app.get("/api/me")
    def me(user: str = Depends(current_user)) -> dict:
        return {"email": user, "dev_mode": dev_mode()}

    @app.get("/")
    def index() -> HTMLResponse:
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        html = html.replace("__BASE__", base_path()).replace("__API_BASE__", os.environ.get("DISKOS_API_BASE", ""))
        return HTMLResponse(html)

    @app.get("/api/wells")
    def list_wells(user: str = Depends(current_user)) -> list[dict]:
        # IDs only; there are thousands of wells, so counts load per-well on demand.
        root = diskos_root(load_config())
        return [{"well_id": wid} for wid in wells_mod.list_well_ids(root)]

    @app.get("/api/corpus")
    def corpus_stats(user: str = Depends(current_user)) -> dict:
        from . import corpus

        index = corpus.build_index(diskos_root(load_config()))
        return corpus.stats(index)

    @app.get("/api/formations")
    def formations_list(level: str = None, user: str = Depends(current_user)) -> dict:
        from .. import formations as fm

        tops_by_well, _ = _tops_and_records()
        return {"formations": fm.all_formations(tops_by_well, level=level)}

    @app.get("/api/corpus/find")
    def corpus_find(
        type: str = None, biostrat: bool = False, core: bool = False, quadrant: str = None,
        formation: str = None, user: str = Depends(current_user),
    ) -> dict:
        from . import corpus

        index = corpus.build_index(diskos_root(load_config()))
        matches = corpus.find(index, data_type=type, biostrat=biostrat or None, core=core or None, quadrant=quadrant)
        if formation:
            from .. import formations as fm

            tops_by_well, _ = _tops_and_records()
            have = fm.wells_by_formation(tops_by_well).get(formation, set())
            matches = [m for m in matches if m["well_id"] in have]
        return {"count": len(matches), "wells": matches}

    @app.post("/api/corpus/ask")
    def corpus_ask(body: AskBody, user: str = Depends(current_user)) -> dict:
        from . import assistant, corpus

        s = corpus.stats(corpus.build_index(diskos_root(load_config())))
        coverage = ", ".join(f"{n} {t}" for t, n in s["coverage"].items())
        top_q = ", ".join(f"quadrant {q}: {n}" for q, n in list(s["by_quadrant"].items())[:12])
        context = (
            f"The DISKOS archive has {s['n_wells']} wells. "
            f"Data coverage (wells with each type): {coverage}. "
            f"{s['biostrat']} wells have a biostratigraphy report; {s['core']} have core. "
            f"Wells per quadrant (top): {top_q}."
        )
        prompt = (
            "You are answering a question about the whole Norwegian DISKOS well archive, "
            "using only the corpus statistics below. For requests to list specific wells, "
            "say the Finder should be used. Do not invent numbers.\n\n"
            f"CORPUS STATISTICS:\n{context}\n\nQUESTION: {body.question}"
        )
        try:
            answer = assistant.make_client().ask(prompt, max_tokens=500, temperature=0.2)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Assistant unavailable: {exc}")
        return {"question": body.question, "answer": answer, "stats": s}

    @app.get("/api/compare")
    def compare_logs(wells: str, mnemonic: str = None, user: str = Depends(current_user)) -> dict:
        from . import workflow

        root = diskos_root(load_config())
        valid = set(wells_mod.list_well_ids(root))
        resolved, missing = [], []
        for wid in (w.strip() for w in wells.split(",") if w.strip()):
            (resolved if wid in valid else missing).append(wid)
        if not resolved:
            raise HTTPException(status_code=404, detail="None of those wells were found.")
        objs = [wells_mod.well_files(root, wid) for wid in resolved]
        try:
            out = workflow.compare_logs(objs, mnemonic)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        out["missing"] = missing
        return out

    @app.get("/api/analyze")
    def analyze_formation(
        wells: str, formation: str = None, top: float = None, bottom: float = None,
        user: str = Depends(current_user),
    ) -> dict:
        from . import analysis, assistant

        root = diskos_root(load_config())
        valid = set(wells_mod.list_well_ids(root))
        resolved, not_found = [], []
        for wid in (w.strip() for w in wells.split(",") if w.strip()):
            (resolved if wid in valid else not_found).append(wid)
        if not resolved:
            raise HTTPException(status_code=404, detail="None of those wells were found.")
        objs = [wells_mod.well_files(root, wid) for wid in resolved]
        tops_by_well, records = _tops_and_records()
        try:
            client = assistant.make_client()
        except Exception:
            client = None
        out = analysis.analyze(
            objs, formation=formation, top=top, bottom=bottom,
            tops_by_well=tops_by_well, records=records, client=client,
        )
        out["not_found"] = not_found
        return out

    @app.get("/api/map")
    def wells_map(formation: str = None, user: str = Depends(current_user)) -> dict:
        from .. import npd as npd_mod
        from ..wiki.mapdata import map_points

        key = str(wiki_dir())
        if key not in _MAP_CACHE:
            pts = map_points(wiki_dir())
            _tops, records = _tops_and_records()
            for p in pts:  # enrich once with NPD year (drilled) + well type for filters
                rec = npd_mod.match(records, p["borehole_id"])
                p["year"] = rec.year if rec else None
                p["well_type"] = rec.well_type if rec else None
            _MAP_CACHE[key] = pts
        points = _MAP_CACHE[key]
        if formation:  # flag which wells have the chosen formation
            from .. import formations as fm

            tops_by_well, _ = _tops_and_records()
            have = fm.wells_by_formation(tops_by_well).get(formation, set())
            points = [{**p, "match": p["borehole_id"] in have} for p in points]
        return {"count": len(points), "points": points}

    @app.get("/api/wiki/search")
    def wiki_search(q: str, user: str = Depends(current_user)) -> dict:
        from ..wiki.search import search as wiki_search_fn

        results = wiki_search_fn(wiki_dir(), q, top_k=10)
        return {
            "query": q,
            "results": [
                {"path": r["path"].name, "score": r["score"], "snippet": r["snippet"]}
                for r in results
            ],
        }

    @app.get("/api/wells/{well_id}/wiki")
    def well_wiki(well_id: str, user: str = Depends(current_user)) -> dict:
        from ..boreholes import borehole_id

        bid = borehole_id(well_id, _npd_records())
        page = wiki_dir() / "entities" / f"well_{bid}.md"
        if not page.is_file():
            return {"borehole_id": bid, "exists": False, "markdown": "", "detail": "No wiki page yet for this borehole. Run `diskos wiki build`."}
        return {"borehole_id": bid, "exists": True, "markdown": page.read_text(encoding="utf-8")}

    @app.get("/api/fields/{name}/wiki")
    def field_wiki(name: str, user: str = Depends(current_user)) -> dict:
        from ..wiki.ingest import field_slug

        page = wiki_dir() / "entities" / f"field_{field_slug(name)}.md"
        if not page.is_file():
            return {"field": name, "exists": False, "markdown": "", "detail": "No wiki page yet for this field."}
        return {"field": name, "exists": True, "markdown": page.read_text(encoding="utf-8")}

    @app.get("/api/wells/{well_id}")
    def well_detail(well_id: str, user: str = Depends(current_user)) -> dict:
        w = _well_or_404(well_id)
        return {
            "well_id": well_id,
            "counts": w.counts(),
            "files": {
                t: [{"name": p.name, "rel": str(p.relative_to(w.path))} for p in ps]
                for t, ps in w.files.items()
            },
            "biostrat": [
                p.name for ps in w.files.values() for p in ps if wells_mod.is_biostrat(p)
            ],
        }

    @app.get("/api/wells/{well_id}/file")
    def well_file(well_id: str, path: str, user: str = Depends(current_user)) -> FileResponse:
        # Serve a file from within the well directory. Guard against traversal:
        # the resolved target must live under the (resolved) well root.
        well = _well_or_404(well_id)
        well_root = well.path.resolve()
        target = (well_root / path).resolve()
        if target != well_root and well_root not in target.parents:
            raise HTTPException(status_code=403, detail="Path escapes the well directory.")
        if not target.is_file():
            raise HTTPException(status_code=404, detail="File not found.")
        # inline so PDFs/images render in the browser tab instead of downloading.
        return FileResponse(target, content_disposition_type="inline")

    @app.get("/api/wells/{well_id}/logs")
    def well_logs(well_id: str, mnemonic: str = None, user: str = Depends(current_user)) -> dict:
        return {"well_id": well_id, "files": _well_logs(well_id, mnemonic)}

    @app.get("/api/wells/{well_id}/graph")
    def well_graph(well_id: str, user: str = Depends(current_user)) -> dict:
        from . import graph

        return graph.build_well_graph(_well_or_404(well_id))

    @app.post("/api/workflow/run")
    def workflow_run(body: WorkflowBody, user: str = Depends(current_user)) -> dict:
        from . import workflow

        well = _well_or_404(body.well_id)
        try:
            output = workflow.run(well, body.kind, body.mnemonic, body.instruction)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Could not run workflow: {exc}")
        return {"well_id": body.well_id, **output}

    @app.post("/api/wells/{well_id}/ask")
    def well_ask(well_id: str, body: AskBody, user: str = Depends(current_user)) -> dict:
        from . import assistant

        well = _well_or_404(well_id)
        try:
            result = assistant.answer_question(well, body.question)
        except Exception as exc:  # model/endpoint unreachable
            raise HTTPException(status_code=503, detail=f"Assistant unavailable: {exc}")
        return {"well_id": well_id, "question": body.question, **result}

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
        redirect_uri = os.environ.get("DISKOS_OAUTH_REDIRECT") or str(request.url_for("auth_callback"))
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
        return RedirectResponse(url=os.environ.get("DISKOS_FRONTEND_URL") or base_path())

    @app.get("/auth/logout")
    async def logout(request: Request):
        request.session.pop("user", None)
        return RedirectResponse(url=os.environ.get("DISKOS_FRONTEND_URL") or base_path())


# Module-level app for `uvicorn diskos.web.api:app`.
app = create_app()
