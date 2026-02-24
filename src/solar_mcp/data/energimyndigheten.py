"""Energimyndigheten solar panel data loader.

Data source
-----------
Statistik om nätanslutna solcellsanläggningar:
https://www.energimyndigheten.se/statistik/officiell-energistatistik/
tillforsel-och-anvandning/natanslutna-solcellsanlaggningar/

The data is published as Excel (.xlsx) files, one per year, containing:
  Columns (Swedish): Kommun, Antal anläggningar, Installerad effekt (kW)

Loading strategy
----------------
1. If ``data/processed/solar_installations.parquet`` exists, load it.
2. Else if any ``data/raw/*.xlsx`` files exist, parse them and cache to Parquet.
3. Otherwise fall back to embedded sample data (realistic 2019–2024 figures).

All text is loaded with UTF-8 and Swedish characters (å, ä, ö) are preserved.
"""

from __future__ import annotations

import io
import logging
import os
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths (resolved relative to this file so they work from any CWD)
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[3]
_RAW_DIR = _REPO_ROOT / "data" / "raw"
_PROCESSED_DIR = _REPO_ROOT / "data" / "processed"
_PARQUET_PATH = _PROCESSED_DIR / "solar_installations.parquet"

# ---------------------------------------------------------------------------
# Embedded sample data (realistic approximations for Swedish municipalities)
# Units: capacity in kW, based on publicly available Energimyndigheten reports
# ---------------------------------------------------------------------------
_SAMPLE_CSV = """\
municipality,year,num_installations,capacity_kw
Karlskrona,2019,312,4820
Karlskrona,2020,480,7640
Karlskrona,2021,710,11900
Karlskrona,2022,1050,19200
Karlskrona,2023,1480,28500
Karlskrona,2024,1920,38700
Malmö,2019,2100,42000
Malmö,2020,3200,66000
Malmö,2021,4900,102000
Malmö,2022,7100,155000
Malmö,2023,9800,221000
Malmö,2024,12500,295000
Göteborg,2019,3500,68000
Göteborg,2020,5200,104000
Göteborg,2021,7800,162000
Göteborg,2022,11000,238000
Göteborg,2023,15200,340000
Göteborg,2024,19500,455000
Stockholm,2019,4800,95000
Stockholm,2020,7100,146000
Stockholm,2021,10500,224000
Stockholm,2022,14900,329000
Stockholm,2023,20200,462000
Stockholm,2024,26000,620000
Lund,2019,1200,23000
Lund,2020,1800,36000
Lund,2021,2700,55000
Lund,2022,3900,83000
Lund,2023,5300,116000
Lund,2024,6800,153000
Helsingborg,2019,1500,29000
Helsingborg,2020,2200,44000
Helsingborg,2021,3400,70000
Helsingborg,2022,4800,104000
Helsingborg,2023,6500,145000
Helsingborg,2024,8400,195000
Uppsala,2019,1800,35000
Uppsala,2020,2700,54000
Uppsala,2021,4100,84000
Uppsala,2022,5800,124000
Uppsala,2023,7900,175000
Uppsala,2024,10200,233000
Linköping,2019,1400,27000
Linköping,2020,2100,43000
Linköping,2021,3200,67000
Linköping,2022,4500,99000
Linköping,2023,6100,139000
Linköping,2024,7900,185000
Västerås,2019,1100,21000
Västerås,2020,1700,34000
Västerås,2021,2600,54000
Västerås,2022,3700,80000
Västerås,2023,5100,115000
Västerås,2024,6600,153000
Gotland,2019,850,17000
Gotland,2020,1300,27000
Gotland,2021,2000,42000
Gotland,2022,2900,63000
Gotland,2023,4000,89000
Gotland,2024,5200,120000
Örebro,2019,980,19000
Örebro,2020,1500,30000
Örebro,2021,2300,48000
Örebro,2022,3300,72000
Örebro,2023,4500,101000
Örebro,2024,5800,133000
Jönköping,2019,880,17000
Jönköping,2020,1350,28000
Jönköping,2021,2050,43000
Jönköping,2022,2950,65000
Jönköping,2023,4050,92000
Jönköping,2024,5250,123000
Varberg,2019,420,8200
Varberg,2020,660,13200
Varberg,2021,1020,20800
Varberg,2022,1480,31200
Varberg,2023,2050,44400
Varberg,2024,2680,59500
Kalmar,2019,380,7400
Kalmar,2020,590,12000
Kalmar,2021,910,18900
Kalmar,2022,1320,28500
Kalmar,2023,1840,40800
Kalmar,2024,2400,54700
Halmstad,2019,720,14000
Halmstad,2020,1100,22200
Halmstad,2021,1680,35100
Halmstad,2022,2420,52600
Halmstad,2023,3300,73400
Halmstad,2024,4300,98500
Karlshamn,2019,180,3400
Karlshamn,2020,280,5400
Karlshamn,2021,430,8500
Karlshamn,2022,630,12800
Karlshamn,2023,880,18400
Karlshamn,2024,1150,24900
"""


def _load_from_parquet() -> Optional[pd.DataFrame]:
    if _PARQUET_PATH.exists():
        logger.info("Loading solar data from %s", _PARQUET_PATH)
        return pd.read_parquet(_PARQUET_PATH)
    return None


def _load_from_excel() -> Optional[pd.DataFrame]:
    """Parse raw Excel files downloaded from Energimyndigheten.

    Expected sheet structure (may vary by year):
        Column A: Kommun (municipality)
        Column B: Antal anläggningar (number of installations)
        Column C: Installerad effekt kW (installed capacity kW)
    """
    xlsx_files = list(_RAW_DIR.glob("*.xlsx"))
    if not xlsx_files:
        return None

    dfs: list[pd.DataFrame] = []
    for fpath in sorted(xlsx_files):
        try:
            xls = pd.ExcelFile(fpath, engine="openpyxl")
            for sheet in xls.sheet_names:
                df = pd.read_excel(
                    xls,
                    sheet_name=sheet,
                    header=0,
                    engine="openpyxl",
                )
                # Try to infer year from filename (e.g. "solceller_2023.xlsx")
                year_candidates = [
                    int(p) for p in fpath.stem.split("_") if p.isdigit() and len(p) == 4
                ]
                year = year_candidates[0] if year_candidates else None

                # Normalise column names
                df.columns = [str(c).strip() for c in df.columns]
                rename_map = {}
                for col in df.columns:
                    lc = col.lower()
                    if "kommun" in lc:
                        rename_map[col] = "municipality"
                    elif "antal" in lc:
                        rename_map[col] = "num_installations"
                    elif "effekt" in lc or "kw" in lc:
                        rename_map[col] = "capacity_kw"
                    elif "år" in lc or "year" in lc:
                        rename_map[col] = "year"
                df = df.rename(columns=rename_map)

                if "municipality" not in df.columns:
                    continue

                if year and "year" not in df.columns:
                    df["year"] = year

                dfs.append(df[["municipality", "year", "num_installations", "capacity_kw"]])
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not parse %s: %s", fpath, exc)

    if not dfs:
        return None

    combined = pd.concat(dfs, ignore_index=True)
    combined["municipality"] = combined["municipality"].astype(str).str.strip()
    combined["capacity_kw"] = pd.to_numeric(combined["capacity_kw"], errors="coerce").fillna(0)
    combined["num_installations"] = pd.to_numeric(
        combined["num_installations"], errors="coerce"
    ).fillna(0).astype(int)

    # Cache to Parquet for future loads
    _PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(_PARQUET_PATH, index=False)
    logger.info("Saved processed data to %s", _PARQUET_PATH)
    return combined


def _load_sample_data() -> pd.DataFrame:
    logger.info("Using embedded sample solar installation data")
    return pd.read_csv(io.StringIO(_SAMPLE_CSV))


# ---------------------------------------------------------------------------
# Module-level cache (loaded once per process)
# ---------------------------------------------------------------------------
_df_cache: Optional[pd.DataFrame] = None


def get_solar_data() -> pd.DataFrame:
    """Return DataFrame with columns: municipality, year, num_installations, capacity_kw."""
    global _df_cache  # noqa: PLW0603
    if _df_cache is not None:
        return _df_cache

    df = _load_from_parquet()
    if df is None:
        df = _load_from_excel()
    if df is None:
        df = _load_sample_data()
    df["capacity_kw"] = df["capacity_kw"].astype(float)
    df["num_installations"] = df["num_installations"].astype(int)
    df["year"] = df["year"].astype(int)
    _df_cache = df
    return df


def get_municipality_data(municipality_name: str) -> pd.DataFrame:
    """Return time-series rows for a single municipality.

    Matching is case-insensitive.  Returns empty DataFrame if not found.
    """
    df = get_solar_data()
    mask = df["municipality"].str.lower() == municipality_name.lower()
    if not mask.any():
        # Try partial match
        mask = df["municipality"].str.lower().str.contains(
            municipality_name.lower(), regex=False
        )
    return df[mask].sort_values("year").reset_index(drop=True)


def list_municipalities_in_data() -> list[str]:
    """Return sorted list of municipality names present in the dataset."""
    df = get_solar_data()
    return sorted(df["municipality"].unique().tolist())
