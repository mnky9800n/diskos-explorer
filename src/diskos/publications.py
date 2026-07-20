"""Find publications about a borehole/field via the Crossref REST API.

Crossref is a free, public bibliographic-metadata service (title, authors, year,
DOI). We only read metadata, we do not fetch or scrape publisher PDFs, so there
is no licensing issue. A ``mailto`` puts requests in Crossref's faster "polite
pool"; the owner sets it via ``DISKOS_CROSSREF_MAILTO`` (referenced by env name,
never stored).

Matching is inherently fuzzy: a borehole id like ``31/2-1`` is specific, a field
name like ``TROLL`` is broad. Callers should present results with that caveat.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

_BASE = "https://api.crossref.org/works"
_SELECT = "title,author,DOI,URL,published,container-title"


def _parse(data: dict) -> list[dict]:
    out: list[dict] = []
    for item in data.get("message", {}).get("items", []):
        title = (item.get("title") or [""])[0].strip()
        if not title:
            continue
        authors = ", ".join(
            a["family"] for a in item.get("author", []) if a.get("family")
        )
        parts = (item.get("published", {}) or {}).get("date-parts", [[None]])
        year = parts[0][0] if parts and parts[0] else None
        out.append({
            "title": title,
            "authors": authors,
            "year": year,
            "doi": item.get("DOI"),
            "url": item.get("URL"),
            "container": (item.get("container-title") or [""])[0],
        })
    return out


def search(query: str, rows: int = 10, mailto: str | None = None, timeout: int = 15) -> list[dict]:
    """Query Crossref for a term; return a list of publication metadata dicts.

    Network errors return [] so a well page never fails on an external outage.
    """
    params = {"query": query, "rows": rows, "select": _SELECT}
    if mailto:
        params["mailto"] = mailto
    url = f"{_BASE}?{urllib.parse.urlencode(params)}"
    agent = f"diskosAI/0.1 (+https://johnspace.xyz{'; mailto:' + mailto if mailto else ''})"
    try:
        request = urllib.request.Request(url, headers={"User-Agent": agent})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return _parse(json.loads(response.read()))
    except Exception:
        return []
