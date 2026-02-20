"""Tests for municipality coordinate mapping."""
import pytest
from solar_mcp.utils.municipality_coords import get_coords, list_municipalities


def test_exact_match():
    coords = get_coords("Karlskrona")
    assert coords is not None
    lat, lon = coords
    # Karlskrona is in southern Sweden
    assert 55.0 < lat < 57.0
    assert 14.0 < lon < 17.0


def test_case_insensitive():
    assert get_coords("karlskrona") == get_coords("Karlskrona")
    assert get_coords("MALMÖ") == get_coords("Malmö")


def test_diacritic_stripping():
    # "Goteborg" should resolve to "Göteborg"
    assert get_coords("Goteborg") == get_coords("Göteborg")
    assert get_coords("Malmo") == get_coords("Malmö")
    assert get_coords("Orebro") == get_coords("Örebro")


def test_unknown_municipality():
    assert get_coords("NonExistentPlace12345") is None


def test_list_municipalities():
    munis = list_municipalities()
    assert "Karlskrona" in munis
    assert "Stockholm" in munis
    assert "Göteborg" in munis
    assert len(munis) > 10
