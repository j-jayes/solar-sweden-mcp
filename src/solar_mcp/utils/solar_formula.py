"""Solar electricity generation formula and supporting constants.

Formula
-------
    Energy (kWh) = Capacity (kW) × Peak_Sun_Hours (h) × Clearness_Index × PR

Where:
    Peak_Sun_Hours  – seasonally adjusted average daily hours of peak irradiance
                     for the given Swedish latitude band.
    Clearness_Index – fraction of clear-sky irradiance, derived from SMHI
                     weather symbol (Wsymb2) or cloud-cover oktas.
    PR              – Performance Ratio (accounts for inverter losses, wiring,
                     temperature, etc.). Default = 0.80.
"""

from __future__ import annotations

import math
from datetime import date

# ---------------------------------------------------------------------------
# SMHI Wsymb2 → clearness index
# Symbol codes: https://opendata.smhi.se/apidocs/metfcst/parameters.html
# ---------------------------------------------------------------------------
WSYMB2_CLEARNESS: dict[int, float] = {
    1: 1.00,   # Clear sky
    2: 0.85,   # Nearly clear
    3: 0.65,   # Variable cloudiness
    4: 0.50,   # Half-clear sky
    5: 0.30,   # Cloudy sky
    6: 0.10,   # Overcast
    7: 0.05,   # Fog
    8: 0.15,   # Light rain showers
    9: 0.10,   # Moderate rain showers
    10: 0.05,  # Heavy rain showers
    11: 0.05,  # Thunderstorm
    12: 0.10,  # Light sleet showers
    13: 0.05,  # Moderate sleet showers
    14: 0.05,  # Heavy sleet showers
    15: 0.20,  # Light snow showers
    16: 0.10,  # Moderate snow showers
    17: 0.05,  # Heavy snow showers
    18: 0.15,  # Light rain
    19: 0.10,  # Moderate rain
    20: 0.05,  # Heavy rain
    21: 0.05,  # Thunder
    22: 0.10,  # Light sleet
    23: 0.05,  # Moderate sleet
    24: 0.05,  # Heavy sleet
    25: 0.20,  # Light snowfall
    26: 0.10,  # Moderate snowfall
    27: 0.05,  # Heavy snowfall
}


def clearness_from_wsymb2(wsymb2: int) -> float:
    """Return clearness index [0–1] for an SMHI weather symbol code."""
    return WSYMB2_CLEARNESS.get(wsymb2, 0.10)


def clearness_from_cloud_oktas(oktas: float) -> float:
    """Return clearness index from cloud cover in oktas (0–8)."""
    oktas = max(0.0, min(8.0, oktas))
    return 1.0 - (oktas / 8.0) * 0.95  # 0.95 so even overcast gives ~6% diffuse


# ---------------------------------------------------------------------------
# Peak sun hours by latitude band and month
# Empirically derived from PVGIS data for Sweden (φ 55°–68°N)
# ---------------------------------------------------------------------------
_PSH_TABLE: dict[int, list[float]] = {
    # Lat band : [Jan, Feb, Mar, Apr, May, Jun, Jul, Aug, Sep, Oct, Nov, Dec]
    55: [0.7, 1.3, 2.8, 4.5, 5.8, 6.2, 6.0, 5.0, 3.3, 1.7, 0.8, 0.5],
    57: [0.5, 1.1, 2.5, 4.2, 5.6, 6.0, 5.8, 4.8, 3.0, 1.5, 0.6, 0.4],
    59: [0.4, 0.9, 2.3, 4.0, 5.5, 5.9, 5.7, 4.6, 2.8, 1.3, 0.5, 0.3],
    61: [0.2, 0.7, 2.0, 3.8, 5.4, 5.8, 5.6, 4.4, 2.5, 1.1, 0.4, 0.2],
    63: [0.1, 0.6, 1.8, 3.6, 5.3, 5.7, 5.5, 4.2, 2.3, 0.9, 0.3, 0.1],
    66: [0.0, 0.4, 1.5, 3.3, 5.0, 5.5, 5.3, 4.0, 2.0, 0.7, 0.1, 0.0],
}


def peak_sun_hours(latitude: float, reference_date: date | None = None) -> float:
    """Return average daily peak sun hours for a given latitude and date.

    Uses monthly averages; defaults to today if *reference_date* is None.
    """
    if reference_date is None:
        reference_date = date.today()
    month_idx = reference_date.month - 1

    # Find the two nearest latitude bands and interpolate
    lat_bands = sorted(_PSH_TABLE.keys())
    lat = max(lat_bands[0], min(lat_bands[-1], latitude))

    lower = max(b for b in lat_bands if b <= lat)
    upper = min(b for b in lat_bands if b >= lat)

    if lower == upper:
        return _PSH_TABLE[lower][month_idx]

    frac = (lat - lower) / (upper - lower)
    psh_low = _PSH_TABLE[lower][month_idx]
    psh_high = _PSH_TABLE[upper][month_idx]
    return psh_low + frac * (psh_high - psh_low)


PERFORMANCE_RATIO = 0.80  # industry standard for utility/residential PV


def expected_energy_kwh(
    capacity_kw: float,
    clearness_index: float,
    latitude: float,
    days: int = 1,
    reference_date: date | None = None,
    performance_ratio: float = PERFORMANCE_RATIO,
) -> float:
    """Return expected electricity generation in kWh over *days* days.

    Parameters
    ----------
    capacity_kw:
        Installed DC capacity in kilowatts.
    clearness_index:
        Fraction of clear-sky irradiance (0–1).
    latitude:
        Geographic latitude of the installation site.
    days:
        Number of days to project over.
    reference_date:
        Date used to select the seasonal peak-sun-hours value.
    performance_ratio:
        System performance ratio (default 0.80).
    """
    psh = peak_sun_hours(latitude, reference_date)
    return capacity_kw * clearness_index * psh * days * performance_ratio


def clear_sky_energy_kwh(
    capacity_kw: float,
    latitude: float,
    days: int = 1,
    reference_date: date | None = None,
    performance_ratio: float = PERFORMANCE_RATIO,
) -> float:
    """Return theoretical maximum generation assuming full clear-sky (index=1.0)."""
    return expected_energy_kwh(
        capacity_kw=capacity_kw,
        clearness_index=1.0,
        latitude=latitude,
        days=days,
        reference_date=reference_date,
        performance_ratio=performance_ratio,
    )
