"""Coordinate helpers: parse LAS header lat/lon and project UTM to WGS84.

A leaf utility with no diskos imports. NPD FactPages already gives decimal-degree
WGS84 coordinates, so this is only needed on the fallback path: reading a well's
location out of a LAS ``~Well Information Block`` (``LATI``/``LONG``, usually in
degrees-minutes-seconds), and, rarely, projecting a well-path UTM survey point.

``pyproj`` is imported lazily (optional ``geo`` extra) so parsing DMS, which is
pure Python, works without it.
"""

from __future__ import annotations

import re

_NUM = re.compile(r"\d+(?:\.\d+)?")


def parse_dms(value: str | None) -> float | None:
    """Parse a latitude/longitude string to signed decimal degrees, or None.

    Handles the LAS header variants seen in the DISKOS archive:
    ``"056 55' 39.864\" N"``, ``"57 34 51.90"``, ``"002 42' 20.689\" E"`` and a
    plain decimal like ``"56.9277"``. Hemisphere S or W makes the result negative.
    A single number is treated as already-decimal degrees.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    nums = [float(n) for n in _NUM.findall(text)]
    if not nums:
        return None
    deg = nums[0]
    minutes = nums[1] if len(nums) > 1 else 0.0
    seconds = nums[2] if len(nums) > 2 else 0.0
    decimal = abs(deg) + minutes / 60.0 + seconds / 3600.0
    upper = text.upper()
    sign = -1.0 if ("S" in upper or "W" in upper or text.lstrip().startswith("-")) else 1.0
    return sign * decimal


def utm_to_wgs84(
    easting: float,
    northing: float,
    zone: int = 31,
    *,
    south: bool = False,
    datum: str = "ED50",
) -> tuple[float, float] | None:
    """Project a UTM point to (lat, lon) in WGS84. Needs the ``geo`` extra (pyproj).

    Norwegian well-path surveys are typically UTM Zone 31/32 on ED50. Returns None
    if pyproj is unavailable so callers can fall back gracefully.
    """
    try:
        from pyproj import Transformer
    except Exception:
        return None
    src = "EPSG:23031" if datum.upper() == "ED50" and zone == 31 else f"+proj=utm +zone={zone} +datum={datum} +units=m +no_defs"
    transformer = Transformer.from_crs(src, "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(easting, northing)
    _ = south  # southern hemisphere unused for the North Sea; kept for completeness
    return (lat, lon)
