"""Coordinate parsing tests (pure, no pyproj)."""

from diskos.geo import parse_dms


def test_parse_dms_variants():
    assert abs(parse_dms('056 55\' 39.864" N') - 56.9277) < 1e-3
    assert abs(parse_dms('002 42\' 20.689" E') - 2.7057) < 1e-3
    assert abs(parse_dms("57 34 51.90") - 57.5810) < 1e-3
    assert abs(parse_dms("56.9277") - 56.9277) < 1e-6


def test_parse_dms_hemisphere_sign():
    assert parse_dms('01 00\' 00" S') < 0
    assert parse_dms('01 00\' 00" W') < 0
    assert parse_dms("-3.5") < 0


def test_parse_dms_empty():
    assert parse_dms("") is None
    assert parse_dms(None) is None
    assert parse_dms("N/A") is None
