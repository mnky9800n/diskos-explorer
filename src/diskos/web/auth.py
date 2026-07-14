"""Authentication and the email allowlist for the web front end.

Jack signs in with Google (OIDC); only allowlisted emails reach any data or model
endpoint. The Google flow needs GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET to run, so
without them the app still starts but real login is disabled. For local dev and
tests, DISKOS_WEB_DEV=1 accepts an X-Dev-User header instead of Google.

Environment:
  DISKOS_WEB_DEV=1                 enable dev auth (X-Dev-User header)
  DISKOS_ALLOWLIST=a@x.com,b@y.com comma-separated allowed emails
  GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET   real OIDC credentials
  DISKOS_SESSION_SECRET            session-cookie signing key
"""

from __future__ import annotations

import os

from fastapi import HTTPException, Request, status


def dev_mode() -> bool:
    return os.environ.get("DISKOS_WEB_DEV") == "1"


def allowlist() -> set[str]:
    raw = os.environ.get("DISKOS_ALLOWLIST", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def is_allowed(email: str | None) -> bool:
    """Whether an email may access the app.

    In dev mode with no explicit allowlist, any email is accepted. Otherwise the
    email must be on the allowlist (an empty allowlist in prod denies everyone,
    which is the safe default).
    """
    if not email:
        return False
    allowed = allowlist()
    if dev_mode() and not allowed:
        return True
    return email.lower() in allowed


def current_user(request: Request) -> str:
    """FastAPI dependency: return the signed-in, allowlisted user's email or 401/403.

    Dev mode reads X-Dev-User; otherwise the email comes from the session set by
    the Google OAuth callback.
    """
    if dev_mode():
        email = request.headers.get("X-Dev-User", "dev@local")
    else:
        email = request.session.get("user") if hasattr(request, "session") else None

    if not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not signed in.")
    if not is_allowed(email):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"{email} is not allowlisted.")
    return email
