"""MCP Tool: estimate_solar_revenue

Estimates the electricity revenue that a municipality's installed solar capacity
would generate on a given day, combining:
  • SMHI weather forecast (clearness index)
  • Installed solar capacity (Energimyndigheten data)
  • Nord Pool day-ahead electricity price (via mgrey.se)
  • Swedish SE pricing zone for the municipality

Also shows the clear-sky maximum revenue and the impact of cloud cover.
For border municipalities it shows the price in the adjacent zone for comparison.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from solar_mcp.data.energimyndigheten import get_municipality_data
from solar_mcp.data.smhi_client import average_clearness, fetch_forecast, wsymb2_description
from solar_mcp.data.nordpool_client import get_average_price, fetch_day_ahead_prices
from solar_mcp.utils.municipality_coords import get_coords
from solar_mcp.utils.municipality_regions import (
    get_region,
    get_border_info,
    is_border_municipality,
)
from solar_mcp.utils.solar_formula import (
    clear_sky_energy_kwh,
    expected_energy_kwh,
)

logger = logging.getLogger(__name__)


def estimate_solar_revenue(
    municipality_name: str,
    days_ahead: int = 1,
    currency: str = "SEK",
) -> dict[str, Any]:
    """Estimate electricity revenue for a municipality's solar capacity on a given day.

    Parameters
    ----------
    municipality_name:
        Swedish municipality (e.g. "Lund", "Varberg", "Stockholm").
    days_ahead:
        0 = today, 1 = tomorrow (default), up to 9.
    currency:
        "SEK" (default) or "EUR".

    Returns
    -------
    dict with keys:
        municipality, se_region, delivery_date, currency,
        installed_capacity_kw,
        forecast_generation_kwh, clear_sky_generation_kwh,
        avg_clearness_index, dominant_weather,
        avg_price_per_mwh,
        estimated_revenue, clear_sky_revenue, cloud_revenue_loss,
        is_border_municipality, adjacent_regions, adjacent_region_prices,
        summary (str)
    """
    days_ahead = max(0, min(9, days_ahead))
    currency = currency.upper()
    if currency not in {"SEK", "EUR"}:
        currency = "SEK"

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

    # --- SE pricing region ---
    se_region = get_region(municipality_name)
    if se_region is None:
        se_region = "SE3"  # default to SE3 if unknown
        region_note = f"SE region unknown for '{municipality_name}'; defaulted to SE3."
    else:
        region_note = None

    # --- Delivery date ---
    today = date.today()
    if days_ahead == 0:
        delivery_date = today
        date_label = "today"
    elif days_ahead == 1:
        delivery_date = today + timedelta(days=1)
        date_label = "tomorrow"
    else:
        delivery_date = today + timedelta(days=days_ahead)
        date_label = f"in {days_ahead} days"
    delivery_date_str = delivery_date.isoformat()

    # --- SMHI forecast ---
    try:
        clearness = average_clearness(lat, lon, days_ahead=max(1, days_ahead))
        forecast_records = fetch_forecast(lat, lon)
    except RuntimeError as exc:
        return {"error": str(exc)}

    # Weather summary: dominant symbol over target day's daytime hours
    from datetime import timezone, datetime
    from collections import Counter
    if days_ahead <= 0:
        window_start = datetime.now(timezone.utc).timestamp()
        window_end = window_start + 86400
    else:
        window_start = (datetime.now(timezone.utc) + timedelta(days=days_ahead - 1)).timestamp()
        window_end = window_start + 86400

    daytime = [
        r for r in forecast_records
        if window_start < r["valid_time"].timestamp() <= window_end
        and 6 <= r["valid_time"].hour <= 20
    ]
    if daytime:
        symbol_counts = Counter(r["wsymb2"] for r in daytime)
        dominant_symbol = symbol_counts.most_common(1)[0][0]
        dominant_weather = wsymb2_description(dominant_symbol)
    else:
        dominant_weather = "Unknown"

    # --- Generation estimates ---
    forecast_kwh = expected_energy_kwh(
        capacity_kw=capacity_kw,
        clearness_index=clearness,
        latitude=lat,
        days=max(1, days_ahead),
        reference_date=delivery_date,
    )
    clear_kwh = clear_sky_energy_kwh(
        capacity_kw=capacity_kw,
        latitude=lat,
        days=max(1, days_ahead),
        reference_date=delivery_date,
    )

    # --- Electricity price ---
    avg_price = get_average_price(
        area=se_region,
        delivery_date=delivery_date_str,
        currency=currency,
    )

    price_note: str | None = None
    if avg_price is None:
        price_note = (
            f"Price data unavailable for {delivery_date_str}. "
            "Nord Pool publishes next-day prices around 13:00 CET."
        )
        # Revenue fields will be None
        estimated_revenue = None
        clear_sky_revenue = None
        cloud_revenue_loss = None
    else:
        # price is currency/MWh; generation is kWh; 1 MWh = 1000 kWh
        price_per_kwh = avg_price / 1000
        estimated_revenue = round(forecast_kwh * price_per_kwh, 2)
        clear_sky_revenue = round(clear_kwh * price_per_kwh, 2)
        cloud_revenue_loss = round(clear_sky_revenue - estimated_revenue, 2)

    # --- Border municipality: adjacent zone price comparison ---
    border_info = get_border_info(municipality_name)
    is_border = border_info is not None
    adjacent_regions: list[str] = []
    adjacent_region_prices: dict[str, Any] = {}

    if is_border and border_info is not None:
        adj = border_info["adjacent_region"]
        adjacent_regions = [adj]
        adj_price = get_average_price(
            area=adj,
            delivery_date=delivery_date_str,
            currency=currency,
        )
        if adj_price is not None:
            adj_per_kwh = adj_price / 1000
            adjacent_region_prices[adj] = {
                "avg_per_mwh": adj_price,
                "estimated_revenue_if_in_this_zone": round(forecast_kwh * adj_per_kwh, 2),
                "clear_sky_revenue_if_in_this_zone": round(clear_kwh * adj_per_kwh, 2),
                "price_difference_per_mwh": round(avg_price - adj_price, 2) if avg_price else None,
            }

    # --- Summary ---
    summary_parts = []
    if region_note:
        summary_parts.append(region_note)

    if avg_price is not None:
        summary_parts.append(
            f"{municipality_name} ({se_region}) is forecast to generate "
            f"~{forecast_kwh:,.0f} kWh {date_label} ({delivery_date_str}), "
            f"worth ~{estimated_revenue:,.0f} {currency} at "
            f"{avg_price:.1f} {currency}/MWh average spot price."
        )
        summary_parts.append(
            f"Under clear skies the generation would be ~{clear_kwh:,.0f} kWh "
            f"(~{clear_sky_revenue:,.0f} {currency}). "
            f"Cloud cover ('{dominant_weather}') reduces revenue by "
            f"~{cloud_revenue_loss:,.0f} {currency}."
        )
        if is_border and adjacent_region_prices:
            adj_zone = adjacent_regions[0]
            adj_data = adjacent_region_prices[adj_zone]
            diff = adj_data.get("price_difference_per_mwh")
            if diff is not None:
                # diff = primary_price - adj_price; positive means adj is cheaper
                direction = "lower" if diff > 0 else "higher"
                summary_parts.append(
                    f"Note: {municipality_name} is a border municipality. "
                    f"Adjacent zone {adj_zone} averages "
                    f"{adj_data['avg_per_mwh']:.1f} {currency}/MWh "
                    f"({abs(diff):.1f} {currency}/MWh {direction} than {se_region}), "
                    f"which would yield ~{adj_data['estimated_revenue_if_in_this_zone']:,.0f} {currency}."
                )
    else:
        summary_parts.append(
            f"{municipality_name} ({se_region}) is forecast to generate "
            f"~{forecast_kwh:,.0f} kWh {date_label}. "
            f"Electricity price data for {delivery_date_str} is not yet available."
        )

    result: dict[str, Any] = {
        "municipality": municipality_name,
        "se_region": se_region,
        "delivery_date": delivery_date_str,
        "currency": currency,
        "installed_capacity_kw": round(capacity_kw, 1),
        "installed_capacity_data_year": data_year,
        "forecast_generation_kwh": round(forecast_kwh, 1),
        "clear_sky_generation_kwh": round(clear_kwh, 1),
        "avg_clearness_index": round(clearness, 3),
        "dominant_weather": dominant_weather,
        "avg_price_per_mwh": avg_price,
        "price_unit": f"{currency}/MWh",
        "estimated_revenue": estimated_revenue,
        "clear_sky_revenue": clear_sky_revenue,
        "cloud_revenue_loss": cloud_revenue_loss,
        "is_border_municipality": is_border,
        "adjacent_regions": adjacent_regions,
        "adjacent_region_prices": adjacent_region_prices,
        "summary": " ".join(summary_parts),
    }

    if price_note:
        result["price_note"] = price_note
    if region_note:
        result["region_note"] = region_note

    return result
