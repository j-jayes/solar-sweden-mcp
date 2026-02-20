"""Tests for Energimyndigheten data loader (uses embedded sample data)."""
import pytest
from solar_mcp.data.energimyndigheten import (
    get_solar_data,
    get_municipality_data,
    list_municipalities_in_data,
)


def test_get_solar_data_returns_dataframe():
    df = get_solar_data()
    assert not df.empty
    assert "municipality" in df.columns
    assert "year" in df.columns
    assert "capacity_kw" in df.columns
    assert "num_installations" in df.columns


def test_karlskrona_data_present():
    df = get_municipality_data("Karlskrona")
    assert not df.empty
    assert (df["municipality"] == "Karlskrona").all()


def test_capacity_increases_over_time():
    df = get_municipality_data("Karlskrona").sort_values("year")
    capacities = df["capacity_kw"].tolist()
    # Should be monotonically increasing
    assert all(capacities[i] <= capacities[i + 1] for i in range(len(capacities) - 1))


def test_case_insensitive_lookup():
    df_upper = get_municipality_data("MALMÖ")
    df_lower = get_municipality_data("malmö")
    assert len(df_upper) == len(df_lower)


def test_unknown_municipality_returns_empty():
    df = get_municipality_data("XYZNonexistent99")
    assert df.empty


def test_list_municipalities_has_karlskrona():
    munis = list_municipalities_in_data()
    assert "Karlskrona" in munis
    assert len(munis) > 5
