#!/usr/bin/env python3
"""Process raw Energimyndigheten Excel files into a single Parquet file.

Usage
-----
    python scripts/process_solar_data.py

Place downloaded .xlsx files from Energimyndigheten in data/raw/ before running.
The script produces data/processed/solar_installations.parquet.

Expected Excel structure (columns may vary slightly by year):
    Kommun | Antal anläggningar | Installerad effekt (kW)

Run this once after downloading new data files.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add src/ to path so we can import solar_mcp without installing
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from solar_mcp.data.energimyndigheten import (
    _RAW_DIR,
    _PROCESSED_DIR,
    _PARQUET_PATH,
    _load_from_excel,
    _load_sample_data,
)


def main() -> None:
    xlsx_files = list(_RAW_DIR.glob("*.xlsx"))
    if not xlsx_files:
        print(f"No .xlsx files found in {_RAW_DIR}")
        print("Download files from:")
        print("  https://www.energimyndigheten.se/statistik/officiell-energistatistik/")
        print("  tillforsel-och-anvandning/natanslutna-solcellsanlaggningar/")
        print()
        print("Generating sample data instead...")
        df = _load_sample_data()
    else:
        print(f"Found {len(xlsx_files)} file(s) in {_RAW_DIR}")
        df = _load_from_excel()
        if df is None:
            print("Failed to parse Excel files — check column names.")
            sys.exit(1)

    _PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(_PARQUET_PATH, index=False)
    print(f"Saved {len(df):,} rows → {_PARQUET_PATH}")
    print(f"Municipalities: {df['municipality'].nunique()}")
    print(f"Years: {sorted(df['year'].unique())}")


if __name__ == "__main__":
    main()
