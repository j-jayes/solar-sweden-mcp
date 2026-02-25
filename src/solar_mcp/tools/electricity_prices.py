"""MCP Tool: get_electricity_prices

Returns Nord Pool day-ahead electricity spot prices for the four Swedish
pricing zones (SE1, SE2, SE3, SE4) for a given date.

Data is sourced from mgrey.se/espot which aggregates public Nord Pool prices.
"""

from __future__ import annotations

import logging
from typing import Any

from solar_mcp.data.nordpool_client import fetch_day_ahead_prices
from solar_mcp.utils.municipality_regions import get_border_municipalities

logger = logging.getLogger(__name__)

_AREA_NAMES = {
    "SE1": "Luleå (Northern Sweden)",
    "SE2": "Sundsvall (Central-North Sweden)",
    "SE3": "Stockholm (Central Sweden)",
    "SE4": "Malmö (Southern Sweden)",
}


def get_electricity_prices(
    delivery_date: str = "today",
    currency: str = "SEK",
    areas: list[str] | None = None,
    include_border_municipalities: bool = False,
) -> dict[str, Any]:
    """Return day-ahead electricity spot prices for Swedish SE pricing zones.

    Parameters
    ----------
    delivery_date:
        "today", "tomorrow", or an ISO date "YYYY-MM-DD".
    currency:
        "SEK" (default) or "EUR".  Prices are per MWh.
    areas:
        Which zones to include.  Defaults to all four: SE1, SE2, SE3, SE4.
    include_border_municipalities:
        If True, also returns the border municipalities table.

    Returns
    -------
    dict with keys:
        delivery_date, currency, unit,
        prices_per_area (dict area → {avg, min, max, hourly}),
        cheapest_area, most_expensive_area,
        spread_se3_se4 (SEK/EUR difference),
        spread_se2_se3 (SEK/EUR difference),
        border_municipalities (list, only when include_border_municipalities=True),
        summary (str)
    """
    if areas is None:
        areas = ["SE1", "SE2", "SE3", "SE4"]

    data = fetch_day_ahead_prices(
        delivery_date=delivery_date,
        currency=currency,
        areas=areas,
    )

    if "error" in data:
        return {
            "error": data["error"],
            "delivery_date": data.get("date", delivery_date),
            "note": (
                "Tomorrow's prices are published by Nord Pool around 13:00 CET. "
                "If requesting tomorrow before that time, prices may not yet be available."
            ),
        }

    resolved_date = data["date"]
    currency_used = data["currency"]
    unit = data["unit"]

    raw_areas = data.get("areas", {})
    if not raw_areas or all(len(v) == 0 for v in raw_areas.values()):
        return {
            "error": f"No price data available for {resolved_date}.",
            "delivery_date": resolved_date,
            "note": (
                "Tomorrow's prices are published by Nord Pool around 13:00 CET. "
                "If requesting tomorrow before that time, prices may not yet be available."
            ),
        }

    prices_per_area: dict[str, Any] = {}
    area_averages: dict[str, float] = {}

    for area, hourly in raw_areas.items():
        if not hourly:
            continue
        values = [h["price"] for h in hourly]
        avg = round(sum(values) / len(values), 2)
        area_averages[area] = avg
        prices_per_area[area] = {
            "area_name": _AREA_NAMES.get(area, area),
            "avg_per_mwh": avg,
            "min_per_mwh": round(min(values), 2),
            "max_per_mwh": round(max(values), 2),
            "hourly": hourly,
        }

    if not area_averages:
        return {"error": "No price data found in API response.", "delivery_date": resolved_date}

    cheapest = min(area_averages, key=area_averages.get)  # type: ignore[arg-type]
    most_expensive = max(area_averages, key=area_averages.get)  # type: ignore[arg-type]

    # Zone spreads (useful for border municipality analysis)
    spread_se3_se4: float | None = None
    if "SE3" in area_averages and "SE4" in area_averages:
        spread_se3_se4 = round(area_averages["SE4"] - area_averages["SE3"], 2)

    spread_se2_se3: float | None = None
    if "SE2" in area_averages and "SE3" in area_averages:
        spread_se2_se3 = round(area_averages["SE3"] - area_averages["SE2"], 2)

    # Build summary
    area_parts = []
    for area in ["SE1", "SE2", "SE3", "SE4"]:
        if area in area_averages:
            area_parts.append(f"{area}: {area_averages[area]:.1f} {currency_used}/MWh")

    summary_parts = [
        f"Day-ahead electricity prices for {resolved_date} ({currency_used}/MWh): "
        + ", ".join(area_parts) + "."
    ]
    if cheapest != most_expensive:
        price_diff = area_averages[most_expensive] - area_averages[cheapest]
        pct_diff = price_diff / area_averages[cheapest] * 100
        summary_parts.append(
            f"{most_expensive} is the most expensive zone at "
            f"{area_averages[most_expensive]:.1f} {currency_used}/MWh "
            f"(+{pct_diff:.0f}% vs cheapest {cheapest} at {area_averages[cheapest]:.1f})."
        )
    if spread_se3_se4 is not None:
        summary_parts.append(
            f"SE4 vs SE3 spread: {spread_se3_se4:+.1f} {currency_used}/MWh."
        )

    result: dict[str, Any] = {
        "delivery_date": resolved_date,
        "currency": currency_used,
        "unit": unit,
        "prices_per_area": prices_per_area,
        "cheapest_area": cheapest,
        "most_expensive_area": most_expensive,
        "spread_se3_se4": spread_se3_se4,
        "spread_se2_se3": spread_se2_se3,
        "summary": " ".join(summary_parts),
    }

    if include_border_municipalities:
        result["border_municipalities"] = get_border_municipalities()

    return result


def list_zone_border_municipalities() -> dict[str, Any]:
    """Return the table of municipalities that sit on SE pricing zone borders.

    These municipalities are located on or near a zone boundary, meaning
    customers in the same municipality may experience different electricity prices.
    """
    borders = get_border_municipalities()
    se2_se3 = [b for b in borders if b["border_type"] == "SE2/SE3"]
    se3_se4 = [b for b in borders if b["border_type"] == "SE3/SE4"]

    return {
        "total_border_municipalities": len(borders),
        "se2_se3_border": {
            "count": len(se2_se3),
            "description": "These municipalities sit on the SE2/SE3 boundary. "
                           "SE3 prices are typically significantly higher than SE2.",
            "municipalities": se2_se3,
        },
        "se3_se4_border": {
            "count": len(se3_se4),
            "description": "These municipalities sit on the SE3/SE4 boundary. "
                           "SE4 prices are often slightly higher than SE3, but can diverge significantly.",
            "municipalities": se3_se4,
        },
        "summary": (
            f"{len(borders)} municipalities in Sweden lie on a pricing zone boundary. "
            f"{len(se2_se3)} are on the SE2/SE3 border (Gävleborg/Dalarna counties) and "
            f"{len(se3_se4)} are on the SE3/SE4 border "
            f"(Halland, Jönköping, and Kalmar counties). "
            "Customers in border municipalities may be in different price zones "
            "depending on their exact grid connection point."
        ),
    }
