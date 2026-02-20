"""MCP Tool: find_optimal_solar_region

Ranks Swedish municipalities by two dimensions:
  1. Sunniest — highest forecast clearness index
  2. Most generation — highest absolute kWh (clearness × capacity)

This lets Copilot Studio answer: "Where is sunniest? And where will
actually generate the most power despite being less sunny?"
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import date, datetime, timezone
from typing import Any

from solar_mcp.data.energimyndigheten import get_solar_data
from solar_mcp.data.smhi_client import average_clearness, fetch_forecast, wsymb2_description
from solar_mcp.utils.municipality_coords import MUNICIPALITY_COORDS, get_coords
from solar_mcp.utils.solar_formula import expected_energy_kwh

logger = logging.getLogger(__name__)

# Municipalities we query weather for (subset with data in both sources)
_CANDIDATE_MUNICIPALITIES = [
    "Karlskrona", "Malmö", "Göteborg", "Stockholm", "Lund",
    "Helsingborg", "Uppsala", "Linköping", "Västerås", "Gotland",
    "Örebro", "Jönköping", "Varberg", "Kalmar", "Halmstad",
]


def find_optimal_solar_region(days_ahead: int = 7) -> dict[str, Any]:
    """Rank municipalities by sunniness and expected generation.

    Parameters
    ----------
    days_ahead:
        Forecast horizon in days (1–10, default 7).

    Returns
    -------
    dict with keys:
        sunniest_region (dict)        – municipality with highest clearness
        most_generation_region (dict) – municipality with highest kWh
        rankings (list of dicts)      – all candidates ranked by generation
        insight (str)                 – narrative comparison paragraph
    """
    days_ahead = max(1, min(10, days_ahead))

    # Load latest installed capacity per municipality
    df = get_solar_data()
    latest_year = df["year"].max()
    latest_df = df[df["year"] == latest_year].copy()
    capacity_map: dict[str, float] = dict(
        zip(latest_df["municipality"], latest_df["capacity_kw"].astype(float))
    )

    today = date.today()
    rankings: list[dict[str, Any]] = []

    for muni in _CANDIDATE_MUNICIPALITIES:
        coords = get_coords(muni)
        if coords is None:
            continue
        capacity_kw = capacity_map.get(muni, 0.0)
        if capacity_kw == 0:
            continue

        lat, lon = coords

        try:
            clearness = average_clearness(lat, lon, days_ahead=days_ahead)
            records = fetch_forecast(lat, lon)
        except RuntimeError as exc:
            logger.warning("Could not fetch forecast for %s: %s", muni, exc)
            continue

        gen_kwh = expected_energy_kwh(
            capacity_kw=capacity_kw,
            clearness_index=clearness,
            latitude=lat,
            days=days_ahead,
            reference_date=today,
        )

        # Dominant weather symbol
        now = datetime.now(timezone.utc)
        daytime = [
            r for r in records
            if now.timestamp() < r["valid_time"].timestamp() <= now.timestamp() + days_ahead * 86400
            and 6 <= r["valid_time"].hour <= 20
        ]
        if daytime:
            symbol_counts = Counter(r["wsymb2"] for r in daytime)
            dominant_symbol = symbol_counts.most_common(1)[0][0]
        else:
            dominant_symbol = 3

        rankings.append(
            {
                "municipality": muni,
                "capacity_kw": round(capacity_kw, 0),
                "clearness_index": round(clearness, 3),
                "forecast_generation_kwh": round(gen_kwh, 1),
                "dominant_weather": wsymb2_description(dominant_symbol),
                "latitude": lat,
            }
        )

    if not rankings:
        return {
            "error": "Could not retrieve forecasts for any municipality. "
                     "Check network connectivity to SMHI API."
        }

    by_clearness = sorted(rankings, key=lambda r: r["clearness_index"], reverse=True)
    by_generation = sorted(rankings, key=lambda r: r["forecast_generation_kwh"], reverse=True)

    sunniest = by_clearness[0]
    most_gen = by_generation[0]

    # Build insight narrative
    if sunniest["municipality"] == most_gen["municipality"]:
        insight = (
            f"{sunniest['municipality']} wins on both fronts: it will be the sunniest region "
            f"(clearness index {sunniest['clearness_index']:.2f}) AND will generate the most "
            f"electricity ({most_gen['forecast_generation_kwh']:,.0f} kWh) over the next "
            f"{days_ahead} day(s)."
        )
    else:
        capacity_ratio = most_gen["capacity_kw"] / max(sunniest["capacity_kw"], 1)
        insight = (
            f"The sunniest region over the next {days_ahead} day(s) will be "
            f"{sunniest['municipality']} (clearness index {sunniest['clearness_index']:.2f}, "
            f"weather: {sunniest['dominant_weather']}). "
            f"However, {most_gen['municipality']} will generate the most electricity "
            f"({most_gen['forecast_generation_kwh']:,.0f} kWh) because it has "
            f"{capacity_ratio:.1f}× more installed capacity "
            f"({most_gen['capacity_kw']:,.0f} kW vs {sunniest['capacity_kw']:,.0f} kW), "
            f"more than compensating for its cloudier skies "
            f"(clearness {most_gen['clearness_index']:.2f})."
        )

    return {
        "sunniest_region": sunniest,
        "most_generation_region": most_gen,
        "rankings_by_generation": by_generation,
        "rankings_by_clearness": by_clearness,
        "days_ahead": days_ahead,
        "insight": insight,
    }
