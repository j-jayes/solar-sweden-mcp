"""Tests for solar generation formula."""
import pytest
from datetime import date
from solar_mcp.utils.solar_formula import (
    clearness_from_wsymb2,
    clearness_from_cloud_oktas,
    peak_sun_hours,
    expected_energy_kwh,
    clear_sky_energy_kwh,
    WSYMB2_CLEARNESS,
)


def test_wsymb2_clearness_clear_sky():
    assert clearness_from_wsymb2(1) == 1.0


def test_wsymb2_clearness_overcast():
    assert clearness_from_wsymb2(6) < 0.2


def test_wsymb2_clearness_unknown_defaults_to_low():
    assert clearness_from_wsymb2(99) == 0.10


def test_wsymb2_all_symbols_in_range():
    for symbol, value in WSYMB2_CLEARNESS.items():
        assert 0.0 <= value <= 1.0, f"Symbol {symbol} out of range: {value}"


def test_clearness_from_cloud_oktas_zero():
    # 0 oktas = clear sky → near 1.0
    assert clearness_from_cloud_oktas(0) > 0.9


def test_clearness_from_cloud_oktas_full():
    # 8 oktas = fully overcast → low but nonzero (diffuse light)
    val = clearness_from_cloud_oktas(8)
    assert 0.0 < val < 0.2


def test_peak_sun_hours_summer_higher_than_winter():
    lat = 57.0
    summer = peak_sun_hours(lat, date(2024, 6, 21))
    winter = peak_sun_hours(lat, date(2024, 12, 21))
    assert summer > winter


def test_peak_sun_hours_south_higher_than_north():
    summer = date(2024, 6, 21)
    south = peak_sun_hours(55.0, summer)
    north = peak_sun_hours(65.0, summer)
    assert south >= north


def test_expected_energy_kwh_basic():
    energy = expected_energy_kwh(
        capacity_kw=100,
        clearness_index=1.0,
        latitude=57.0,
        days=1,
        reference_date=date(2024, 6, 21),
    )
    # Should be positive and reasonable (> 0, < 1000 kWh for 100 kW over 1 day)
    assert 0 < energy < 1000


def test_expected_energy_scales_with_capacity():
    kwargs = dict(clearness_index=0.8, latitude=57.0, days=7, reference_date=date(2024, 6, 1))
    e100 = expected_energy_kwh(capacity_kw=100, **kwargs)
    e200 = expected_energy_kwh(capacity_kw=200, **kwargs)
    assert abs(e200 - 2 * e100) < 0.01


def test_clear_sky_higher_than_cloudy():
    kwargs = dict(capacity_kw=1000, latitude=57.0, days=7, reference_date=date(2024, 6, 1))
    cloudy = expected_energy_kwh(clearness_index=0.3, **kwargs)
    clear = clear_sky_energy_kwh(**kwargs)
    assert clear > cloudy
