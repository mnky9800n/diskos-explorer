# Web front end

The **backend** exists and is tested: a FastAPI app in `src/diskos/web/` that
reuses the pipeline modules (`io`, `palyno`, `wells`) and gates every data
endpoint behind Google OAuth + an email allowlist. The **front-end UI** (the
actual pages Jack clicks) is the remaining piece.

## Run it (dev mode, no Google needed)

```bash
uv sync --extra web
DISKOS_WEB_DEV=1 DISKOS_ROOT=./tests/data/diskos_sample uv run diskos serve
# then:
curl localhost:8000/health
curl localhost:8000/api/wells                       # dev user is auto-accepted
curl localhost:8000/api/wells/7_11-1/palynology
```

## Endpoints

- `GET /health` (open)
- `GET /api/wells` catalog of boreholes
- `GET /api/wells/{id}` a well's files by type
- `GET /api/wells/{id}/palynology` the reconciled depth x species table (plus any
  similar names still awaiting a same/different decision)
- `GET /auth/login` / `/auth/callback` / `/auth/logout` Google OIDC

## What still needs decisions / secrets (the current wall)

- **Google OAuth credentials**: set `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`
  (and register the callback URL) to enable real login. Without them the app runs
  in dev mode only.
- **Allowlist**: `DISKOS_ALLOWLIST=jack@example.com,you@example.com`.
- **Session secret**: `DISKOS_SESSION_SECRET` in production.
- **Front-end framework and hosting**: not chosen yet (likely a small SPA served
  by this app, hosted on Modal). Endpoints above are what it will consume.
