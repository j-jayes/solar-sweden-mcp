"""MCP Tool: get_solar_growth

Returns historical solar panel installation growth for a Swedish municipality,
including year-over-year percentage growth and CAGR.
"""

from __future__ import annotations

import logging
from typing import Any

from solar_mcp.data.energimyndigheten import get_municipality_data, list_municipalities_in_data

logger = logging.getLogger(__name__)


def get_solar_growth(municipality_name: str) -> dict[str, Any]:
    """Return historical solar growth metrics for *municipality_name*.

    Returns
    -------
    dict with keys:
        municipality (str)
        data (list of yearly records)
        yoy_growth (list of year-over-year % growth in capacity)
        cagr (float | None): compound annual growth rate over the full data range, in %
        latest_year (int)
        latest_capacity_kw (float)
        latest_installations (int)
        summary (str): human-readable summary sentence
    """
    df = get_municipality_data(municipality_name)

    if df.empty:
        available = list_municipalities_in_data()
        return {
            "error": f"No data found for '{municipality_name}'. "
                     f"Available municipalities include: {', '.join(available[:10])}",
        }

    rows = df.to_dict(orient="records")

    # Year-over-year growth
    yoy: list[dict] = []
    for i in range(1, len(rows)):
        prev = rows[i - 1]
        curr = rows[i]
        if prev["capacity_kw"] > 0:
            pct = round((curr["capacity_kw"] - prev["capacity_kw"]) / prev["capacity_kw"] * 100, 1)
        else:
            pct = None
        yoy.append(
            {
                "year": curr["year"],
                "capacity_kw": curr["capacity_kw"],
                "growth_pct": pct,
            }
        )

    # CAGR over the full data range
    cagr: float | None = None
    if len(rows) >= 2:
        first = rows[0]
        last = rows[-1]
        n_years = last["year"] - first["year"]
        if n_years > 0 and first["capacity_kw"] > 0:
            cagr = round(
                ((last["capacity_kw"] / first["capacity_kw"]) ** (1 / n_years) - 1) * 100, 1
            )

    latest = rows[-1]
    most_recent_yoy = yoy[-1]["growth_pct"] if yoy else None

    # Build summary sentence
    summary_parts = [
        f"{municipality_name} had {latest['num_installations']:,} solar installations "
        f"with {latest['capacity_kw']:,.0f} kW of capacity in {latest['year']}."
    ]
    if most_recent_yoy is not None:
        summary_parts.append(
            f"Capacity grew by {most_recent_yoy:.1f}% in {latest['year']} compared to the previous year."
        )
    if cagr is not None:
        n = rows[-1]["year"] - rows[0]["year"]
        summary_parts.append(
            f"The {n}-year compound annual growth rate (CAGR) of installed capacity is {cagr:.1f}%."
        )

    return {
        "municipality": municipality_name,
        "data": rows,
        "yoy_growth": yoy,
        "cagr": cagr,
        "latest_year": latest["year"],
        "latest_capacity_kw": latest["capacity_kw"],
        "latest_installations": latest["num_installations"],
        "summary": " ".join(summary_parts),
    }
