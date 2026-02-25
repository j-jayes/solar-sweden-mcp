"""MCP Tool: get_fastest_growth

Returns a ranked list of Swedish municipalities by solar panel growth rate
between two specified years.  Supports ranking by either installed capacity (kW)
or number of installations.
"""

from __future__ import annotations

import logging
from typing import Any

from solar_mcp.data.energimyndigheten import get_solar_data

logger = logging.getLogger(__name__)

_VALID_METRICS = {"capacity", "installations"}


def get_fastest_growth(
    start_year: int,
    end_year: int,
    metric: str = "capacity",
    top_n: int = 10,
) -> dict[str, Any]:
    """Return municipalities ranked by solar growth rate between two years.

    Parameters
    ----------
    start_year:
        First year of the comparison window (inclusive).
    end_year:
        Last year of the comparison window (inclusive).
    metric:
        "capacity"      – rank by growth in installed capacity (kW)
        "installations" – rank by growth in number of installations
    top_n:
        How many top municipalities to return (default 10).

    Returns
    -------
    dict with keys:
        metric, start_year, end_year, unit,
        rankings (list of ranked municipalities),
        total_municipalities_compared,
        summary (str)
    """
    metric = metric.lower()
    if metric not in _VALID_METRICS:
        return {
            "error": f"Invalid metric '{metric}'. Choose 'capacity' or 'installations'."
        }

    if start_year >= end_year:
        return {"error": f"start_year ({start_year}) must be before end_year ({end_year})."}

    top_n = max(1, min(top_n, 50))

    df = get_solar_data()

    available_years = sorted(df["year"].unique().tolist())
    if start_year not in available_years:
        return {
            "error": f"No data for {start_year}. Available years: {available_years}",
        }
    if end_year not in available_years:
        return {
            "error": f"No data for {end_year}. Available years: {available_years}",
        }

    col = "capacity_kw" if metric == "capacity" else "num_installations"
    unit = "kW" if metric == "capacity" else "installations"

    start_df = df[df["year"] == start_year][["municipality", col]].rename(
        columns={col: "start_value"}
    )
    end_df = df[df["year"] == end_year][["municipality", col]].rename(
        columns={col: "end_value"}
    )

    merged = start_df.merge(end_df, on="municipality", how="inner")
    # Only keep municipalities with a positive start value (avoid divide-by-zero)
    merged = merged[merged["start_value"] > 0].copy()

    if merged.empty:
        return {"error": "No municipalities found with data in both years."}

    merged["growth_pct"] = (
        (merged["end_value"] - merged["start_value"]) / merged["start_value"] * 100
    ).round(1)

    merged = merged.sort_values("growth_pct", ascending=False).reset_index(drop=True)
    total = len(merged)

    top = merged.head(top_n)
    rankings = []
    for rank, row in enumerate(top.itertuples(), start=1):
        rankings.append(
            {
                "rank": rank,
                "municipality": row.municipality,
                "start_value": round(float(row.start_value), 1),
                "end_value": round(float(row.end_value), 1),
                "growth_pct": row.growth_pct,
                "unit": unit,
            }
        )

    if not rankings:
        return {"error": "Could not compute rankings."}

    top_muni = rankings[0]
    metric_label = "installed capacity" if metric == "capacity" else "number of installations"
    summary = (
        f"The fastest-growing municipality in {metric_label} between {start_year} and "
        f"{end_year} was {top_muni['municipality']} with +{top_muni['growth_pct']:.1f}% "
        f"(from {top_muni['start_value']:,.0f} to {top_muni['end_value']:,.0f} {unit}). "
        f"{total} municipalities had data for both years."
    )

    return {
        "metric": metric,
        "start_year": start_year,
        "end_year": end_year,
        "unit": unit,
        "top_n": len(rankings),
        "total_municipalities_compared": total,
        "rankings": rankings,
        "summary": summary,
    }
