"""Extract borehole map points from the built wiki pages.

The wiki build already resolved every borehole's coordinates and wrote them into
each page's YAML front matter (lat/lon/field/block/borehole_id). The map reads
that back rather than recomputing, so the corpus map is just a cheap scan of the
entities directory. Pages without coordinates (Danish/non-NPD wells not resolved)
are skipped, which is honest: we only place what we can locate.
"""

from __future__ import annotations

from pathlib import Path

_FIELDS = ("borehole_id", "lat", "lon", "field", "block", "coord_source")


def _front_matter(text: str) -> dict:
    """Parse the leading ``--- ... ---`` YAML-ish block into a flat dict."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    out: dict = {}
    for line in text[3:end].splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            out[key.strip()] = value.strip()
    return out


def _point(text: str) -> dict | None:
    fm = _front_matter(text)
    lat, lon = fm.get("lat", ""), fm.get("lon", "")
    if not lat or not lon:
        return None
    try:
        latf, lonf = float(lat), float(lon)
    except ValueError:
        return None
    return {
        "borehole_id": fm.get("borehole_id", ""),
        "lat": latf,
        "lon": lonf,
        "field": fm.get("field") or None,
        "block": fm.get("block") or None,
        "coord_source": fm.get("coord_source") or None,
        # cheap flags parsed from the rendered body
        "biostrat": "[biostrat]" in text,
        "has_logs": "## Well logs\n\n- " in text,
    }


def map_points(wiki_dir: str | Path) -> list[dict]:
    """Located boreholes as map points, read from the wiki entity pages."""
    entities = Path(wiki_dir) / "entities"
    if not entities.is_dir():
        return []
    points: list[dict] = []
    for page in sorted(entities.glob("well_*.md")):
        point = _point(page.read_text(encoding="utf-8"))
        if point is not None:
            points.append(point)
    return points
