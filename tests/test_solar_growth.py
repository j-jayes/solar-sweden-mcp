"""Tests for get_solar_growth tool (uses embedded sample data, no network)."""
import pytest
from solar_mcp.tools.solar_growth import get_solar_growth


def test_karlskrona_growth_has_expected_keys():
    result = get_solar_growth("Karlskrona")
    assert "error" not in result
    assert result["municipality"] == "Karlskrona"
    assert "data" in result
    assert "yoy_growth" in result
    assert "cagr" in result
    assert "latest_capacity_kw" in result
    assert "summary" in result


def test_growth_data_is_chronological():
    result = get_solar_growth("Malmö")
    years = [row["year"] for row in result["data"]]
    assert years == sorted(years)


def test_cagr_is_positive_for_growing_market():
    result = get_solar_growth("Stockholm")
    assert result["cagr"] > 0


def test_yoy_growth_values_are_positive():
    result = get_solar_growth("Göteborg")
    for entry in result["yoy_growth"]:
        if entry["growth_pct"] is not None:
            assert entry["growth_pct"] > 0


def test_unknown_municipality_returns_error():
    result = get_solar_growth("MadeUpPlace999")
    assert "error" in result


def test_summary_is_non_empty_string():
    result = get_solar_growth("Lund")
    assert isinstance(result["summary"], str)
    assert len(result["summary"]) > 20
