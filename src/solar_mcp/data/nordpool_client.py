"""Electricity spot price client — Swedish SE1/SE2/SE3/SE4 day-ahead prices.

Data source
-----------
mgrey.se/espot — a public aggregator of Nord Pool day-ahead prices for Sweden.
No API key required.  Prices are sourced from Nord Pool and published for
open use.

Endpoint:
    https://mgrey.se/espot?format=json&date=YYYY-MM-DD

Response shape:
    {
      "date": "YYYY-MM-DD",
      "SE1": [{"hour": 0-23, "price_eur": float, "price_sek": float, "kmeans": int}, ...],
      "SE2": [...],
      "SE3": [...],
      "SE4": [...]
    }

Prices in the API response are in öre/kWh (price_sek) and eurocents/kWh (price_eur).
This module converts them to SEK/MWh and EUR/MWh (multiply by 10) so that the
rest of the codebase can work with standard market units.
"""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://mgrey.se/espot"
_VALID_AREAS = {"SE1", "SE2", "SE3", "SE4"}

# ---------------------------------------------------------------------------
# Simple in-memory TTL cache (same pattern as smhi_client.py)
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
# Date helpers
# ---------------------------------------------------------------------------

def _resolve_date(delivery_date: str) -> str:
    """Resolve 'today' / 'tomorrow' to an ISO date string (YYYY-MM-DD).

    Any other string is returned unchanged (assumed to already be ISO format).
    """
    today = date.today()
    if delivery_date.lower() == "today":
        return today.isoformat()
    if delivery_date.lower() == "tomorrow":
        return (today + timedelta(days=1)).isoformat()
    return delivery_date


# ---------------------------------------------------------------------------
# API fetch
# ---------------------------------------------------------------------------

def fetch_day_ahead_prices(
    delivery_date: str = "today",
    currency: str = "SEK",
    areas: list[str] | None = None,
) -> dict[str, Any]:
    """Fetch day-ahead electricity prices for Swedish SE zones.

    Parameters
    ----------
    delivery_date:
        "today", "tomorrow", or an ISO date string "YYYY-MM-DD".
    currency:
        "SEK" or "EUR" (case-insensitive).
    areas:
        List of SE zone codes to include.  Defaults to all four zones.

    Returns
    -------
    dict with keys:
        date        – resolved ISO date string
        currency    – "SEK" or "EUR"
        areas       – dict mapping area code → list of hourly price dicts
                      Each hourly entry: {hour, price}
        error       – present only on failure
    """
    if areas is None:
        areas = ["SE1", "SE2", "SE3", "SE4"]

    currency = currency.upper()
    if currency not in {"SEK", "EUR"}:
        currency = "SEK"

    price_field = "price_sek" if currency == "SEK" else "price_eur"
    resolved_date = _resolve_date(delivery_date)

    cache_key = f"nordpool:{resolved_date}"
    raw = _cache_get(cache_key)

    if raw is None:
        try:
            resp = httpx.get(
                _BASE_URL,
                params={"format": "json", "date": resolved_date},
                timeout=10.0,
            )
            resp.raise_for_status()
            raw = resp.json()
            _cache_set(cache_key, raw)
        except httpx.HTTPError as exc:
            logger.warning("Nordpool price fetch failed: %s", exc)
            return {"error": f"Price API unavailable: {exc}", "date": resolved_date}
        except Exception as exc:  # noqa: BLE001
            logger.warning("Nordpool price parse error: %s", exc)
            return {"error": f"Price API error: {exc}", "date": resolved_date}

    result_areas: dict[str, list[dict]] = {}
    for area in areas:
        if area not in _VALID_AREAS:
            continue
        hourly_raw = raw.get(area, [])
        # mgrey.se returns öre/kWh (SEK) and eurocents/kWh (EUR).
        # Multiply by 10 to convert to standard market units (SEK/MWh or EUR/MWh).
        # Derivation: 1 öre/kWh × (100 öre/SEK)⁻¹ × 1000 kWh/MWh = 10 SEK/MWh
        result_areas[area] = [
            {"hour": entry["hour"], "price": round(entry[price_field] * 10, 2)}
            for entry in hourly_raw
        ]

    return {
        "date": resolved_date,
        "currency": currency,
        "unit": f"{currency}/MWh",
        "areas": result_areas,
    }


def get_average_price(
    area: str,
    delivery_date: str = "today",
    currency: str = "SEK",
) -> float | None:
    """Return the average day-ahead price (currency/MWh) for one area on one day.

    Returns None if data is unavailable.
    """
    data = fetch_day_ahead_prices(delivery_date=delivery_date, currency=currency, areas=[area])
    if "error" in data:
        return None
    hourly = data.get("areas", {}).get(area, [])
    if not hourly:
        return None
    return round(sum(e["price"] for e in hourly) / len(hourly), 2)
