#!/usr/bin/env python3
"""Download Sweden municipality GeoJSON from okfse/sweden-geojson.

Usage
-----
    python scripts/download_geo.py

Output
------
    data/geo/municipalities.geojson

GeoJSON feature property schema
--------------------------------
    kom_namn  str  — municipality name in Swedish, e.g. "Malmö"
    id        str  — 4-digit municipality code, e.g. "1280"

The 'id' field matches the 'municipality_code' column produced by
download_solar_data.py, enabling a reliable code-based join.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

_REPO_ROOT = Path(__file__).resolve().parent.parent
_GEO_DIR = _REPO_ROOT / "data" / "geo"
_GEO_PATH = _GEO_DIR / "municipalities.geojson"

_GEO_URL = (
    "https://raw.githubusercontent.com/okfse/sweden-geojson/"
    "master/swedish_municipalities.geojson"
)


def main() -> None:
    _GEO_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Downloading: {_GEO_URL}")
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        r = client.get(_GEO_URL)
        r.raise_for_status()

    data = r.json()
    features = data.get("features", [])
    n = len(features)
    print(f"Downloaded {n} municipality features")

    if n == 0:
        print("ERROR: no features found in GeoJSON", file=sys.stderr)
        sys.exit(1)

    # Validate expected property keys
    first_props = features[0]["properties"]
    print(f"Feature properties: {list(first_props.keys())}")

    if "kom_namn" not in first_props:
        print(
            f"WARNING: expected 'kom_namn' property, got: {list(first_props.keys())}. "
            "The solar_map tool uses 'kom_namn' for municipality names.",
            file=sys.stderr,
        )
    if "id" not in first_props:
        print(
            f"WARNING: expected 'id' property (municipality code), "
            f"got: {list(first_props.keys())}.",
            file=sys.stderr,
        )

    # Sample output
    print("\nSample municipalities:")
    for feat in features[:5]:
        p = feat["properties"]
        print(f"  id={p.get('id','?')!r:8s}  kom_namn={p.get('kom_namn','?')!r}")

    _GEO_PATH.write_text(r.text, encoding="utf-8")
    print(f"\nSaved → {_GEO_PATH}  ({_GEO_PATH.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    try:
        main()
    except httpx.HTTPError as exc:
        print(f"HTTP error: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
