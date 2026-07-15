"""Read the ``~Well Information Block`` header out of a LAS file. Pure IO.

``welllog/curves.read_las`` calls ``lasio(...).df()`` and keeps only the curve
data, discarding the header. But that header carries the well's identity and
surface location (``WELL``, ``FLD``, ``LATI``, ``LONG``, ``UWI``), which the wiki
needs for wells NPD FactPages does not cover. This reads just the header
(``ignore_data=True`` skips the large data section) and returns the raw values.

Latitude/longitude come back as the raw header strings (usually DMS); converting
them to decimal degrees is left to the caller (``geo.parse_dms``) so this module
stays a pure parser with no analysis dependency.
"""

from __future__ import annotations

from pathlib import Path

# LAS header mnemonic -> our field name. Operators vary, so a few aliases each.
_FIELDS = {
    "well": ("WELL", "WELLNAME"),
    "field": ("FLD", "FIELD"),
    "country": ("NATI", "CTRY", "COUN"),
    "uwi": ("UWI", "API", "APIN", "PBWE"),
    "lat_dms": ("LATI", "LAT"),
    "lon_dms": ("LONG", "LON"),
    "location": ("LOC",),
}


def _clean(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def read_las_header(path: str | Path) -> dict:
    """Return well identity + location from a LAS header, or {} if unreadable.

    Keys: ``well``, ``field``, ``country``, ``uwi``, ``lat_dms``, ``lon_dms``,
    ``location`` (any may be None). Coordinate values are the raw header strings.
    """
    try:
        import lasio

        las = lasio.read(str(path), ignore_data=True)
    except Exception:
        return {}

    header = {}
    for item in las.well:
        header[item.mnemonic.upper()] = item.value

    out: dict = {}
    for name, aliases in _FIELDS.items():
        value = None
        for alias in aliases:
            if alias in header:
                value = _clean(header[alias])
                if value:
                    break
        out[name] = value
    return out
