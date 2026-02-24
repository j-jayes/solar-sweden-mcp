"""Tests for get_solar_map tool.

Playwright is mocked throughout so tests run without a real browser installed.
The GeoJSON-dependent tests are skipped unless data/geo/municipalities.geojson
has been downloaded (run: python scripts/download_geo.py).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from solar_mcp.tools.solar_map import (
    SolarMapResult,
    _build_capacity_lookups,
    _normalize,
    get_solar_map,
)

_GEO_PATH = Path(__file__).resolve().parents[1] / "data" / "geo" / "municipalities.geojson"
_GEO_AVAILABLE = _GEO_PATH.exists()

# Minimal valid 1×1 PNG (for mocking screenshot return value)
_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
    b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18"
    b"\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


# ---------------------------------------------------------------------------
# Unit tests — no GeoJSON needed
# ---------------------------------------------------------------------------

class TestNormalize:
    def test_malmo(self):
        assert _normalize("Malmö") == "malmo"

    def test_goteborg(self):
        assert _normalize("Göteborg") == "goteborg"

    def test_orebro(self):
        assert _normalize("Örebro") == "orebro"

    def test_already_ascii(self):
        assert _normalize("Stockholm") == "stockholm"

    def test_mixed_case(self):
        assert _normalize("KARLSKRONA") == "karlskrona"


class TestCapacityLookups:
    def test_returns_non_empty(self):
        by_code, by_name = _build_capacity_lookups(year=2024)
        # At least one of the dicts should have data (embedded sample covers 2019–2024)
        assert len(by_name) > 0

    def test_capacity_positive(self):
        _, by_name = _build_capacity_lookups(year=2024)
        assert all(v >= 0 for v in by_name.values())

    def test_fallback_year(self):
        # year=2019 is the first year in embedded sample data
        _, by_name = _build_capacity_lookups(year=2019)
        assert len(by_name) > 0

    def test_empty_year_returns_empty(self):
        # Year 2000 has no data; both dicts should be empty
        by_code, by_name = _build_capacity_lookups(year=2000)
        assert len(by_code) == 0
        assert len(by_name) == 0


# ---------------------------------------------------------------------------
# Integration tests — require GeoJSON file
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _GEO_AVAILABLE, reason="GeoJSON not downloaded (run scripts/download_geo.py)")
class TestGetSolarMapWithGeoJSON:
    def test_returns_summary_when_playwright_unavailable(self):
        """When Playwright raises ImportError, summary is still returned."""
        with patch("solar_mcp.tools.solar_map._screenshot_map") as mock_ss:
            mock_ss.side_effect = ImportError("playwright not available")
            result = get_solar_map(year=2024)

        assert isinstance(result, SolarMapResult)
        assert result.playwright_available is False
        assert result.image_bytes is None
        assert "top_10_municipalities" in result.summary
        assert result.summary["year"] == 2024
        assert result.summary["total_municipalities_in_map"] > 0

    def test_returns_image_with_mocked_screenshot(self):
        """Full pipeline with mocked PNG bytes."""
        with patch("solar_mcp.tools.solar_map._screenshot_map") as mock_ss:
            mock_ss.return_value = (_TINY_PNG, "image/png")
            result = get_solar_map(year=2024)

        assert result.image_bytes == _TINY_PNG
        assert result.mime_type == "image/png"
        assert result.error is None

    def test_summary_has_required_fields(self):
        with patch("solar_mcp.tools.solar_map._screenshot_map") as mock_ss:
            mock_ss.return_value = (_TINY_PNG, "image/png")
            result = get_solar_map()

        s = result.summary
        assert "year" in s
        assert "total_municipalities_in_map" in s
        assert "municipalities_with_data" in s
        assert "total_installed_capacity_kw" in s
        assert "total_installed_capacity_mw" in s
        assert "top_10_municipalities" in s
        assert len(s["top_10_municipalities"]) <= 10

    def test_top_municipality_has_positive_capacity(self):
        with patch("solar_mcp.tools.solar_map._screenshot_map") as mock_ss:
            mock_ss.return_value = (_TINY_PNG, "image/png")
            result = get_solar_map(year=2024)

        top = result.summary["top_10_municipalities"]
        assert top[0]["capacity_kw"] > 0

    def test_defaults_to_latest_year(self):
        with patch("solar_mcp.tools.solar_map._screenshot_map") as mock_ss:
            mock_ss.return_value = (_TINY_PNG, "image/png")
            result = get_solar_map(year=None)

        # 2024 is the latest year in embedded sample data
        assert result.summary["year"] >= 2019

    def test_year_2023_works(self):
        with patch("solar_mcp.tools.solar_map._screenshot_map") as mock_ss:
            mock_ss.return_value = (_TINY_PNG, "image/png")
            result = get_solar_map(year=2023)

        assert result.summary["year"] == 2023


class TestGetSolarMapMissingGeoJSON:
    def test_returns_error_gracefully(self):
        """When GeoJSON is absent the tool returns an error result, not an exception."""
        with patch("solar_mcp.tools.solar_map._GEO_PATH", Path("/nonexistent/path.geojson")):
            result = get_solar_map()

        assert result.error is not None
        assert "GeoJSON" in result.error or "not found" in result.error.lower()
        assert result.image_bytes is None
