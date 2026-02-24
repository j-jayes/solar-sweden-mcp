#!/usr/bin/env python3
"""Download municipality-level solar installation data from Energimyndigheten PxWeb API.

Usage
-----
    python scripts/download_solar_data.py           # full download
    python scripts/download_solar_data.py --dry-run # print API metadata and exit

Output
------
    data/raw/en0123_raw.json                        — raw API response (cached)
    data/processed/solar_installations.parquet      — cleaned DataFrame

Schema produced
---------------
    municipality      str   — Swedish name, e.g. "Malmö"
    municipality_code str   — 4-digit code, e.g. "1280"
    year              int   — 2016–2024
    num_installations int   — antal anläggningar (Total power class)
    capacity_kw       float — installerad effekt converted from MW → kW

API notes (confirmed by inspection)
------------------------------------
    Variable codes: År, Region, Effektklass, Kategori
    Year codes:     '0'='2016', ..., '8'='2024'
    Region codes:   '0'=national, '1'–'21'=counties, '22'–'311'=municipalities
    Effektklass:    '3' = Totalt (all power classes combined)
    Kategori:       '0' = antal anläggningar, '1' = installerad effekt (MW)
    Response format: row-based JSON with key[] and values[] per record
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import httpx
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
_RAW_DIR = _REPO_ROOT / "data" / "raw"
_PROCESSED_DIR = _REPO_ROOT / "data" / "processed"
_RAW_JSON = _RAW_DIR / "en0123_raw.json"
_PARQUET_PATH = _PROCESSED_DIR / "solar_installations.parquet"

# ---------------------------------------------------------------------------
# API — confirmed path from PxWeb navigation
# ---------------------------------------------------------------------------
_BASE = (
    "https://pxexternal.energimyndigheten.se/api/v1/sv/"
    "Energimyndighetens_statistikdatabas/"
    "Officiell_energistatistik/"
    "Natanslutna_solcellsanlaggningar/EN0123_1.px"
)

# Regex: "0114 Upplands Väsby" → group(1)="0114", group(2)="Upplands Väsby"
_MUNI_LABEL_RE = re.compile(r"^(\d{4})\s+(.+)$")


# ---------------------------------------------------------------------------
# Metadata helpers
# ---------------------------------------------------------------------------
def _fetch_metadata(client: httpx.Client) -> dict:
    print(f"GET metadata: {_BASE}")
    r = client.get(_BASE, timeout=30.0)
    r.raise_for_status()
    return r.json()


def _build_lookups(meta: dict) -> tuple[dict, dict, list, list]:
    """Extract lookup tables from API metadata.

    Returns
    -------
    year_lookup : {year_code_str → year_int}  e.g. {'0': 2016, ..., '8': 2024}
    muni_lookup : {region_code_str → (municipality_code, municipality_name)}
    muni_codes  : list[str]  — region codes for municipalities only
    year_codes  : list[str]  — all year codes
    """
    region_var = next(v for v in meta["variables"] if v["code"] == "Region")
    ar_var = next(v for v in meta["variables"] if v["code"] == "År")

    # Year lookup
    year_lookup: dict[str, int] = {}
    for code, label in zip(ar_var["values"], ar_var["valueTexts"]):
        year_lookup[code] = int(label.strip())
    year_codes = ar_var["values"]

    # Municipality lookup (labels starting with 4-digit code)
    muni_lookup: dict[str, tuple[str, str]] = {}
    muni_codes: list[str] = []
    for code, label in zip(region_var["values"], region_var["valueTexts"]):
        m = _MUNI_LABEL_RE.match(label)
        if m:
            muni_lookup[code] = (m.group(1), m.group(2).strip())
            muni_codes.append(code)

    return year_lookup, muni_lookup, muni_codes, year_codes


# ---------------------------------------------------------------------------
# Data fetch
# ---------------------------------------------------------------------------
def _fetch_data(client: httpx.Client, muni_codes: list[str], year_codes: list[str]) -> dict:
    query = {
        "query": [
            {
                "code": "År",
                "selection": {"filter": "item", "values": year_codes},
            },
            {
                "code": "Region",
                "selection": {"filter": "item", "values": muni_codes},
            },
            {
                "code": "Effektklass",
                "selection": {"filter": "item", "values": ["3"]},  # Totalt
            },
            {
                "code": "Kategori",
                "selection": {
                    "filter": "item",
                    "values": ["0", "1"],  # antal, effekt (MW)
                },
            },
        ],
        "response": {"format": "json"},
    }
    print(f"POST query ({len(muni_codes)} municipalities × {len(year_codes)} years)")
    r = client.post(_BASE, json=query, timeout=120.0)
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def _parse_response(
    payload: dict,
    year_lookup: dict[str, int],
    muni_lookup: dict[str, tuple[str, str]],
) -> pd.DataFrame:
    """Parse row-based PxWeb JSON response into a tidy DataFrame.

    Each row in payload['data'] has:
        key   = [year_code, region_code, effektklass_code, kategori_code]
        values = [value_string]
    Kategori '0' = antal, '1' = effekt (MW).
    """
    rows_data = payload["data"]

    # Accumulate: (year_code, region_code) → {antal, effekt_mw}
    staging: dict[tuple[str, str], dict] = {}

    for row in rows_data:
        year_code, region_code, _effekt, kat_code = row["key"]
        val_str = row["values"][0]
        try:
            val = float(val_str)
        except (ValueError, TypeError):
            val = 0.0  # ".." = missing / not available in Swedish statistics

        key = (year_code, region_code)
        if key not in staging:
            staging[key] = {"antal": 0.0, "effekt_mw": 0.0}

        if kat_code == "0":       # antal anläggningar
            staging[key]["antal"] = val
        elif kat_code == "1":     # installerad effekt (MW)
            staging[key]["effekt_mw"] = val

    # Flatten into rows
    records = []
    for (year_code, region_code), vals in staging.items():
        if region_code not in muni_lookup:
            continue
        muni_code, muni_name = muni_lookup[region_code]
        year = year_lookup.get(year_code)
        if year is None:
            continue
        records.append(
            {
                "municipality": muni_name,
                "municipality_code": muni_code,
                "year": year,
                "num_installations": int(round(vals["antal"])),
                "capacity_kw": round(vals["effekt_mw"] * 1000.0, 1),
            }
        )

    df = pd.DataFrame(records).sort_values(["municipality", "year"]).reset_index(drop=True)

    # Sanity check
    max_kw = df["capacity_kw"].max()
    assert max_kw < 100_000_000, (
        f"Suspiciously large capacity {max_kw:.0f} kW — check MW→kW conversion"
    )
    return df


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(dry_run: bool = False) -> None:
    _RAW_DIR.mkdir(parents=True, exist_ok=True)
    _PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    with httpx.Client(follow_redirects=True) as client:
        meta = _fetch_metadata(client)
        year_lookup, muni_lookup, muni_codes, year_codes = _build_lookups(meta)

        if dry_run:
            print("\n=== API Metadata ===")
            for var in meta.get("variables", []):
                print(f"\nVariable: {var['code']} — {var['text']}")
                for val, label in zip(var.get("values", []), var.get("valueTexts", [])):
                    print(f"  {val!r:12s} {label}")
            print(f"\nMunicipality count: {len(muni_codes)}")
            print(f"Year count:         {len(year_codes)} → {list(year_lookup.values())}")
            return

        payload = _fetch_data(client, muni_codes, year_codes)

    raw_rows = len(payload.get("data", []))
    print(f"API returned {raw_rows:,} rows")

    # Cache raw JSON
    _RAW_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Raw JSON cached → {_RAW_JSON}  ({_RAW_JSON.stat().st_size / 1024:.0f} KB)")

    df = _parse_response(payload, year_lookup, muni_lookup)

    n_munis = df["municipality"].nunique()
    years = sorted(df["year"].unique())
    print(f"\nParsed: {len(df):,} rows | {n_munis} municipalities | {years[0]}–{years[-1]}")
    print("Top 5 by capacity (latest year):")
    latest = df[df["year"] == df["year"].max()]
    for _, row in latest.nlargest(5, "capacity_kw").iterrows():
        print(
            f"  {row['municipality_code']}  {row['municipality']:<25} "
            f"{row['capacity_kw']:>12,.0f} kW  ({row['num_installations']:,} installations)"
        )

    df.to_parquet(_PARQUET_PATH, index=False)
    print(f"\nParquet saved → {_PARQUET_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download Energimyndigheten solar data")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch API metadata only; do not download data",
    )
    args = parser.parse_args()
    try:
        main(dry_run=args.dry_run)
    except httpx.HTTPError as exc:
        print(f"HTTP error: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        raise
