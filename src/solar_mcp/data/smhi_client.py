"""SMHI Open Data — Point Forecast API client with in-memory TTL caching.

API docs: https://opendata.smhi.se/apidocs/metfcst/index.html
Endpoint: https://opendata-download-metfcst.smhi.se/api/category/pmp3g/version/2
          /geotype/point/lon/{lon}/lat/{lat}/data.json

License: Creative Commons CC BY 4.0 (free tier, no API key required).
"""

from __future__ import annotations

import time
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from solar_mcp.utils.solar_formula import clearness_from_cloud_layers, clearness_from_wsymb2

logger = logging.getLogger(__name__)

_SMHI_BASE = (
    "https://opendata-download-metfcst.smhi.se/api/category/pmp3g/version/2"
    "/geotype/point/lon/{lon}/lat/{lat}/data.json"
)

# ---------------------------------------------------------------------------
# Simple in-memory TTL cache
# ---------------------------------------------------------------------------
_cache: dict[str, tuple[float, Any]] = {}
_CACHE_TTL_SECONDS = 1800  # 30 minutes


def _cache_get(key: str) -> Any | None:
    entry = _cache.get(key)
    if entry is None:
        return None
    ts, value = entry
    if time.monotonic() - ts > _CACHE_TTL_SECONDS:
        del _cache[key]
        return None
    return value


def _cache_set(key: str, value: Any) -> None:
    _cache[key] = (time.monotonic(), value)


# ---------------------------------------------------------------------------
# Data extraction helpers
# ---------------------------------------------------------------------------

def _extract_parameter(parameters: list[dict], name: str) -> float | None:
    """Pull a scalar value from a SMHI timeSeries parameters list."""
    for p in parameters:
        if p.get("name") == name:
            values = p.get("values", [])
            if values:
                return float(values[0])
    return None


def _parse_time(valid_time: str) -> datetime:
    """Parse SMHI ISO-8601 timestamp to UTC-aware datetime."""
    # Format: "2024-06-01T12:00:00Z"
    return datetime.fromisoformat(valid_time.replace("Z", "+00:00"))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_forecast(lat: float, lon: float) -> list[dict]:
    """Fetch point forecast from SMHI and return parsed hourly records.

    Each record is a dict with:
        valid_time (datetime): UTC timestamp
        wsymb2 (int):          Weather symbol (1=clear … 27=heavy snow)
        temperature (float):   °C
        clearness (float):     Estimated solar clearness index 0–1
        t (float):             Same as temperature (alias)
    """
    cache_key = f"{lat:.3f},{lon:.3f}"
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.debug("SMHI cache hit for (%s, %s)", lat, lon)
        return cached

    url = _SMHI_BASE.format(lat=f"{lat:.4f}", lon=f"{lon:.4f}")
    logger.info("Fetching SMHI forecast: %s", url)

    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.get(url)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(
            f"SMHI API returned HTTP {exc.response.status_code} for ({lat}, {lon})"
        ) from exc
    except httpx.RequestError as exc:
        raise RuntimeError(f"SMHI API request failed: {exc}") from exc

    records: list[dict] = []
    for entry in payload.get("timeSeries", []):
        params = entry.get("parameters", [])
        wsymb2 = int(_extract_parameter(params, "Wsymb2") or 3)
        temp = _extract_parameter(params, "t")

        # Cloud layer cover in oktas (0–8).  All four are always present in
        # pmp3g, but we fall back gracefully if any are missing.
        tcc = _extract_parameter(params, "tcc_mean") or 0.0
        lcc = _extract_parameter(params, "lcc_mean") or 0.0
        mcc = _extract_parameter(params, "mcc_mean") or 0.0
        hcc = _extract_parameter(params, "hcc_mean") or 0.0

        # Prefer the physically-based cloud-layer clearness; fall back to
        # Wsymb2 proxy only if no layer data is available.
        if tcc > 0 or lcc > 0 or mcc > 0 or hcc > 0:
            clearness = clearness_from_cloud_layers(tcc, lcc, mcc, hcc)
        else:
            clearness = clearness_from_wsymb2(wsymb2)

        records.append(
            {
                "valid_time": _parse_time(entry["validTime"]),
                "wsymb2": wsymb2,
                "temperature": temp,
                "t": temp,
                # Cloud cover in oktas (for downstream use)
                "tcc_mean": tcc,
                "lcc_mean": lcc,
                "mcc_mean": mcc,
                "hcc_mean": hcc,
                # Clearness index using weighted cloud layers (preferred)
                "clearness": clearness,
                # Wsymb2-based clearness kept for reference / comparison
                "clearness_wsymb2": clearness_from_wsymb2(wsymb2),
            }
        )

    _cache_set(cache_key, records)
    logger.debug("Fetched %d forecast records for (%s, %s)", len(records), lat, lon)
    return records


def average_clearness(
    lat: float,
    lon: float,
    days_ahead: int = 7,
) -> float:
    """Return the mean clearness index over the next *days_ahead* days.

    Only hours between 06:00 and 20:00 (UTC) are averaged to exclude
    nighttime zeroes which would artificially depress the estimate.
    """
    records = fetch_forecast(lat, lon)
    now = datetime.now(timezone.utc)
    cutoff = now.timestamp() + days_ahead * 86400

    daytime_records = [
        r for r in records
        if now.timestamp() < r["valid_time"].timestamp() <= cutoff
        and 6 <= r["valid_time"].hour <= 20
    ]

    if not daytime_records:
        return 0.5  # Fallback if API returns nothing useful

    return sum(r["clearness"] for r in daytime_records) / len(daytime_records)


def wsymb2_description(wsymb2: int) -> str:
    """Return human-readable English description of an SMHI weather symbol."""
    descriptions = {
        1: "Clear sky",
        2: "Nearly clear sky",
        3: "Variable cloudiness",
        4: "Half-clear sky",
        5: "Cloudy sky",
        6: "Overcast",
        7: "Fog",
        8: "Light rain showers",
        9: "Moderate rain showers",
        10: "Heavy rain showers",
        11: "Thunderstorm",
        12: "Light sleet showers",
        13: "Moderate sleet showers",
        14: "Heavy sleet showers",
        15: "Light snow showers",
        16: "Moderate snow showers",
        17: "Heavy snow showers",
        18: "Light rain",
        19: "Moderate rain",
        20: "Heavy rain",
        21: "Thunder",
        22: "Light sleet",
        23: "Moderate sleet",
        24: "Heavy sleet",
        25: "Light snowfall",
        26: "Moderate snowfall",
        27: "Heavy snowfall",
    }
    return descriptions.get(wsymb2, f"Unknown (code {wsymb2})")
