"""MCP Tool: compare_generation_forecast

Compares the forecast electricity generation for a municipality against the
theoretical clear-sky maximum, showing how much cloud cover is costing.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from solar_mcp.data.energimyndigheten import get_municipality_data
from solar_mcp.data.smhi_client import average_clearness, fetch_forecast
from solar_mcp.utils.municipality_coords import get_coords
from solar_mcp.utils.solar_formula import (
    clear_sky_energy_kwh,
    expected_energy_kwh,
)
from solar_mcp.data.smhi_client import wsymb2_description

logger = logging.getLogger(__name__)


def compare_generation_forecast(
    municipality_name: str,
    days_ahead: int = 7,
) -> dict[str, Any]:
    """Return forecast vs. clear-sky generation comparison for a municipality.

    Parameters
    ----------
    municipality_name:
        Swedish municipality name (e.g. "Karlskrona").
    days_ahead:
        Number of days to forecast ahead (1–10, default 7).

    Returns
    -------
    dict with keys:
        municipality, days_ahead,
        installed_capacity_kw,
        forecast_energy_kwh, clear_sky_energy_kwh,
        cloud_loss_kwh, cloud_loss_pct,
        avg_clearness, weather_summary,
        summary (str)
    """
    days_ahead = max(1, min(10, days_ahead))

    # --- Solar installation data ---
    df = get_municipality_data(municipality_name)
    if df.empty:
        return {"error": f"No solar installation data found for '{municipality_name}'."}
    latest = df.iloc[-1]
    capacity_kw = float(latest["capacity_kw"])
    data_year = int(latest["year"])

    # --- Coordinates ---
    coords = get_coords(municipality_name)
    if coords is None:
        return {
            "error": (
                f"Geographic coordinates not found for '{municipality_name}'. "
                "Try a nearby larger municipality."
            )
        }
    lat, lon = coords

    # --- Weather forecast ---
    try:
        clearness = average_clearness(lat, lon, days_ahead=days_ahead)
        forecast_records = fetch_forecast(lat, lon)
    except RuntimeError as exc:
        return {"error": str(exc)}

    # Weather summary: most common symbol in daytime hours
    from datetime import timezone
    from datetime import datetime
    now = datetime.now(timezone.utc)
    daytime = [
        r for r in forecast_records
        if now.timestamp() < r["valid_time"].timestamp() <= now.timestamp() + days_ahead * 86400
        and 6 <= r["valid_time"].hour <= 20
    ]
    if daytime:
        # Find most frequent Wsymb2
        from collections import Counter
        symbol_counts = Counter(r["wsymb2"] for r in daytime)
        dominant_symbol = symbol_counts.most_common(1)[0][0]
        weather_summary = wsymb2_description(dominant_symbol)
        avg_temp = sum(r["temperature"] for r in daytime if r["temperature"] is not None) / max(
            len(daytime), 1
        )
    else:
        weather_summary = "Unknown"
        avg_temp = None

    # --- Generation estimates ---
    today = date.today()
    forecast_kwh = expected_energy_kwh(
        capacity_kw=capacity_kw,
        clearness_index=clearness,
        latitude=lat,
        days=days_ahead,
        reference_date=today,
    )
    clear_kwh = clear_sky_energy_kwh(
        capacity_kw=capacity_kw,
        latitude=lat,
        days=days_ahead,
        reference_date=today,
    )
    loss_kwh = clear_kwh - forecast_kwh
    loss_pct = (loss_kwh / clear_kwh * 100) if clear_kwh > 0 else 0.0

    # --- Summary sentence ---
    summary = (
        f"Over the next {days_ahead} day(s), {municipality_name} is forecast to generate "
        f"{forecast_kwh:,.0f} kWh from its {capacity_kw:,.0f} kW of installed capacity "
        f"(data from {data_year}). "
        f"Under perfectly clear skies, it could generate {clear_kwh:,.0f} kWh. "
        f"Cloud cover (dominant condition: {weather_summary}) is reducing potential "
        f"generation by {loss_pct:.1f}% — a loss of {loss_kwh:,.0f} kWh."
    )

    result: dict[str, Any] = {
        "municipality": municipality_name,
        "days_ahead": days_ahead,
        "installed_capacity_kw": capacity_kw,
        "installed_capacity_data_year": data_year,
        "forecast_energy_kwh": round(forecast_kwh, 1),
        "clear_sky_energy_kwh": round(clear_kwh, 1),
        "cloud_loss_kwh": round(loss_kwh, 1),
        "cloud_loss_pct": round(loss_pct, 1),
        "avg_clearness_index": round(clearness, 3),
        "dominant_weather": weather_summary,
        "summary": summary,
    }
    if avg_temp is not None:
        result["avg_temperature_c"] = round(avg_temp, 1)

    return result
