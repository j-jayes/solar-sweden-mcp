"""MCP Tool: get_solar_map

Creates a choropleth map of Sweden showing installed solar capacity (kW)
by municipality. The map is rendered via folium (Leaflet) and captured as
a PNG screenshot using Playwright (headless Chromium).

Returns
-------
SolarMapResult:
    .summary      dict  — JSON-serialisable summary (top municipalities, totals)
    .image_bytes  bytes — PNG screenshot, or None if Playwright is unavailable
    .mime_type    str   — "image/png"
    .error        str   — description of any non-fatal error
"""

from __future__ import annotations

import copy
import json
import logging
import os
import tempfile
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import folium
import pandas as pd

from solar_mcp.data.energimyndigheten import get_solar_data

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory PNG cache (keyed by year) — avoids re-running Playwright when
# the /maps/{year}.png endpoint is called shortly after the MCP tool.
# ---------------------------------------------------------------------------
_png_cache: dict[int, bytes] = {}


def get_cached_png(year: int) -> bytes | None:
    """Return cached PNG bytes for *year*, or None if not yet generated."""
    return _png_cache.get(year)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[3]
_GEO_PATH = _REPO_ROOT / "data" / "geo" / "municipalities.geojson"

# ---------------------------------------------------------------------------
# Screenshot settings
# ---------------------------------------------------------------------------
# 1600×900 (16:9 landscape) matches Copilot Studio's image display ratio so
# the full map is visible without top/bottom cropping.
_VIEWPORT_W = 1600
_VIEWPORT_H = 900


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------
@dataclass
class SolarMapResult:
    summary: dict[str, Any]
    image_bytes: bytes | None = None
    mime_type: str = "image/png"
    playwright_available: bool = True
    error: str | None = None


# ---------------------------------------------------------------------------
# Name normalisation (mirrors municipality_coords.py)
# ---------------------------------------------------------------------------
def _normalize(name: str) -> str:
    """Lowercase + strip diacritics for fuzzy municipality name matching."""
    nfd = unicodedata.normalize("NFD", name.lower())
    return "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------
def _build_capacity_lookups(
    year: int,
) -> tuple[dict[str, float], dict[str, float]]:
    """Return two lookup dicts for joining with GeoJSON features.

    Returns
    -------
    capacity_by_code : {municipality_code: capacity_kw}
        Populated when real API data (with municipality_code column) is loaded.
        Empty dict when using embedded sample data.
    capacity_by_name : {normalised_name: capacity_kw}
        Always populated; used as fallback for sample data.
    """
    df = get_solar_data()
    df_year = df[df["year"] == year]

    by_code: dict[str, float] = {}
    by_name: dict[str, float] = {}

    if "municipality_code" in df_year.columns:
        by_code = {
            str(row["municipality_code"]): float(row["capacity_kw"])
            for _, row in df_year.iterrows()
            if pd.notna(row["municipality_code"])
        }

    for _, row in df_year.iterrows():
        by_name[_normalize(str(row["municipality"]))] = float(row["capacity_kw"])

    return by_code, by_name


def _load_geojson() -> dict:
    if not _GEO_PATH.exists():
        raise FileNotFoundError(
            f"GeoJSON not found at {_GEO_PATH}. "
            "Run: python scripts/download_geo.py"
        )
    with open(_GEO_PATH, encoding="utf-8") as f:
        return json.load(f)


def _enrich_geojson(
    geojson: dict,
    by_code: dict[str, float],
    by_name: dict[str, float],
) -> dict:
    """Return a deep-copied GeoJSON with 'capacity_kw' injected into each feature."""
    gj = copy.deepcopy(geojson)
    for feat in gj["features"]:
        props = feat["properties"]
        code = str(props.get("id", ""))
        name = props.get("kom_namn", "")

        kw = by_code.get(code)
        if kw is None:
            kw = by_name.get(_normalize(name), 0.0)
        props["capacity_kw"] = round(kw or 0.0, 1)
    return gj


# ---------------------------------------------------------------------------
# Map building
# ---------------------------------------------------------------------------
def _build_folium_map(enriched_geojson: dict, year: int) -> folium.Map:
    """Build a folium map centred on Sweden with viridis colouring.

    Uses fit_bounds() so Leaflet auto-calculates the zoom that fits all of
    Sweden (55°N–70°N, 10°E–25°E) within the 1600×900 viewport — no manual
    zoom tuning needed.  Viridis is applied via branca.LinearColormap +
    GeoJson style_function because folium.Choropleth.fill_color only accepts
    ColorBrewer palette names.
    """
    import branca.colormap as cm

    m = folium.Map(
        location=[63.0, 16.5],
        zoom_start=5,        # overridden by fit_bounds below
        tiles=None,          # no tile server — fast and deterministic
        prefer_canvas=True,
    )

    # fit_bounds tells Leaflet to zoom/pan so the full Sweden bounding box
    # is visible with a small margin inside the 1600×900 viewport.
    # [SW corner, NE corner] — slight padding outside Sweden's actual extent.
    m.fit_bounds([[54.5, 9.5], [70.0, 25.5]])

    # Use the 95th-percentile as vmax so the colour scale isn't dominated by
    # one or two outlier cities — smaller municipalities show meaningful colour.
    values = sorted(
        feat["properties"].get("capacity_kw", 0) or 0
        for feat in enriched_geojson["features"]
    )
    vmax = values[int(len(values) * 0.95)] if values else 1.0
    if vmax <= 0:
        vmax = 1.0

    # Viridis: dark-purple (low) → blue → teal → green → yellow (high)
    colormap = cm.LinearColormap(
        colors=["#440154", "#3b528b", "#21918c", "#5ec962", "#fde725"],
        vmin=0,
        vmax=vmax,
        caption=f"Installerad soleffekt (kW) — {year}",
    )

    def _style(feature: dict) -> dict:
        raw = feature["properties"].get("capacity_kw", 0) or 0
        clamped = min(float(raw), vmax)
        return {
            "fillColor": colormap(clamped),
            "fillOpacity": 0.85,
            "color": "#555555",
            "weight": 0.4,
        }

    folium.GeoJson(
        enriched_geojson,
        style_function=_style,
        tooltip=folium.GeoJsonTooltip(
            fields=["kom_namn", "capacity_kw"],
            aliases=["Kommun:", "Effekt (kW):"],
            localize=True,
            sticky=False,
        ),
    ).add_to(m)

    m.add_child(colormap)
    return m


# ---------------------------------------------------------------------------
# Screenshot via Playwright
# ---------------------------------------------------------------------------
def _screenshot_map(m: folium.Map) -> tuple[bytes, str]:
    """Render the folium map to a PNG using headless Chromium.

    Raises
    ------
    ImportError   if playwright is not installed
    RuntimeError  on any screenshot failure
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ImportError(
            "playwright is not installed. "
            "Add playwright>=1.40.0 to requirements.txt and run "
            "'playwright install chromium'."
        ) from exc

    # Save map to a temp HTML file
    tmp = tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8")
    tmp_path = tmp.name
    tmp.close()
    m.save(tmp_path)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
            )
            page = browser.new_page(
                viewport={"width": _VIEWPORT_W, "height": _VIEWPORT_H}
            )
            # file:// URL — tiles=None means no network tile requests
            page.goto(f"file:///{tmp_path.replace(os.sep, '/')}", wait_until="networkidle", timeout=15_000)
            # Brief pause for Leaflet polygon rendering to complete
            page.wait_for_timeout(600)
            png_bytes: bytes = page.screenshot(type="png", full_page=False)
            browser.close()
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    return png_bytes, "image/png"


# ---------------------------------------------------------------------------
# Public tool function
# ---------------------------------------------------------------------------
def get_solar_map(year: int | None = None) -> SolarMapResult:
    """Generate a choropleth map of Swedish municipality solar capacity.

    Parameters
    ----------
    year : int, optional
        Year for which to display capacity (2016–2024).
        Defaults to the most recent year in the dataset.

    Returns
    -------
    SolarMapResult
        .summary      — JSON dict with top municipalities and totals
        .image_bytes  — PNG bytes, or None if Playwright is unavailable
    """
    df = get_solar_data()
    if year is None:
        year = int(df["year"].max())

    # Build capacity lookup dicts
    by_code, by_name = _build_capacity_lookups(year)

    # Load and enrich GeoJSON
    try:
        geojson = _load_geojson()
    except FileNotFoundError as exc:
        msg = str(exc)
        logger.error(msg)
        return SolarMapResult(summary={"error": msg}, error=msg)

    enriched = _enrich_geojson(geojson, by_code, by_name)

    # Build summary statistics
    items = [
        {
            "municipality": feat["properties"].get("kom_namn", ""),
            "municipality_code": str(feat["properties"].get("id", "")),
            "capacity_kw": feat["properties"]["capacity_kw"],
        }
        for feat in enriched["features"]
    ]
    items_sorted = sorted(items, key=lambda x: x["capacity_kw"], reverse=True)
    total_kw = sum(x["capacity_kw"] for x in items)
    covered = sum(1 for x in items if x["capacity_kw"] > 0)

    summary: dict[str, Any] = {
        "year": year,
        "total_municipalities_in_map": len(items),
        "municipalities_with_data": covered,
        "total_installed_capacity_kw": round(total_kw, 0),
        "total_installed_capacity_mw": round(total_kw / 1000, 1),
        "top_10_municipalities": items_sorted[:10],
        "data_source": (
            "Energimyndigheten EN0123 via PxWeb API"
            if by_code
            else "Embedded sample data (run scripts/download_solar_data.py for real data)"
        ),
    }

    # Build and screenshot the map
    try:
        folium_map = _build_folium_map(enriched, year)
    except Exception as exc:
        logger.exception("Failed to build folium map")
        return SolarMapResult(
            summary=summary,
            error=f"Map build failed: {exc}",
        )

    try:
        img_bytes, mime = _screenshot_map(folium_map)
        logger.info("Screenshot: %d bytes, %s", len(img_bytes), mime)
        _png_cache[year] = img_bytes  # cache so /maps/{year}.png is instant
        return SolarMapResult(summary=summary, image_bytes=img_bytes, mime_type=mime)
    except ImportError:
        logger.warning("Playwright not available — returning text summary only")
        return SolarMapResult(
            summary=summary,
            image_bytes=None,
            playwright_available=False,
        )
    except Exception as exc:
        logger.exception("Screenshot failed")
        return SolarMapResult(
            summary=summary,
            image_bytes=None,
            error=f"Screenshot failed: {exc}",
        )
