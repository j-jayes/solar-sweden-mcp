# Solar Sweden MCP — Project Plan
**Date:** 2026-02-20  
**Goal:** Demonstrate MCP + Copilot Studio with real Swedish solar & weather data

---

## 1. Executive Summary

This project builds an **MCP (Model Context Protocol) server** that gives an AI assistant (Copilot Studio) access to:

1. **Historical solar panel installation data** from Energimyndigheten (Swedish Energy Agency)
2. **Live weather forecasts** from SMHI (Swedish Meteorological and Hydrological Institute)

The combined data lets Copilot Studio answer rich, data-driven questions like:
- *"Where has solar capacity grown the fastest in Sweden?"*
- *"How much power will Karlskrona generate this week vs. a clear-sky scenario?"*
- *"Which Swedish region has the best combination of sun and installed capacity right now?"*

---

## 2. Architecture Overview

```
Copilot Studio (Client)
        │  HTTP POST /messages (Streamable HTTP / SSE)
        ▼
  Azure Container App
  ┌─────────────────────────────────┐
  │  FastAPI Application            │
  │  ┌───────────────────────────┐  │
  │  │  MCP Server (mcp SDK)     │  │
  │  │  Tools:                   │  │
  │  │  • get_solar_growth       │  │
  │  │  • compare_generation_    │  │
  │  │    forecast               │  │
  │  │  • find_optimal_solar_    │  │
  │  │    region                 │  │
  │  └───────────────────────────┘  │
  │  Data Layer:                    │
  │  • Energimyndigheten (static)   │
  │  • SMHI API (live + cached)     │
  └─────────────────────────────────┘
```

---

## 3. Data Sources

### 3.1 Energimyndigheten — Solar Panel Statistics
- **URL:** https://www.energimyndigheten.se/statistik/officiell-energistatistik/tillforsel-och-anvandning/natanslutna-solcellsanlaggningar/
- **Format:** Excel (.xlsx) files, one per year, per county/municipality
- **Key columns:**
  - `Kommun` (Municipality name)
  - `År` (Year)
  - `Antal anläggningar` (Number of installations)
  - `Installerad effekt (kW)` (Installed capacity in kW)
- **Update cadence:** Static (annual release); we embed 2019–2024 data
- **Action:** Download Excel files, convert to Parquet for fast loading

### 3.2 SMHI Open Data — Point Forecast API
- **Base URL:** `https://opendata-download-metfcst.smhi.se/api/category/pmp3g/version/2/geotype/point/lon/{lon}/lat/{lat}/data.json`
- **License:** Creative Commons CC BY 4.0 (free)
- **Key parameters returned:**
  - `t` — Air temperature (°C)
  - `Wsymb2` — Weather symbol (1 = clear sky → 27 = heavy snow)
  - `lcc_mean` — Low cloud cover (0–8 oktas)
  - `mcc_mean` — Medium cloud cover (0–8 oktas)
  - `hcc_mean` — High cloud cover (0–8 oktas)
- **Update cadence:** Fresh every request (with in-memory TTL cache = 30 min)

---

## 4. Municipality Coordinate Mapping

The SMHI API requires decimal latitude/longitude while Energimyndigheten data is keyed by municipality name. A static dictionary `MUNICIPALITY_COORDS` maps 290 Swedish municipalities:

```python
MUNICIPALITY_COORDS = {
    "Karlskrona": (56.1612, 15.5869),
    "Stockholm":  (59.3293, 18.0686),
    "Göteborg":   (57.7089, 11.9746),
    ...
}
```

Characters å, ä, ö are handled with UTF-8 throughout; fuzzy matching handles user typos.

---

## 5. Solar Generation Formula

```
Expected Power (kWh over period) =
    Installed Capacity (kW)
    × Clearness Index (0–1)
    × Peak Sun Hours (hrs)
    × Performance Ratio (0.8)
```

**Clearness Index** from SMHI `Wsymb2`:
| Symbol | Description | Index |
|--------|-------------|-------|
| 1 | Clear sky | 1.00 |
| 2 | Nearly clear | 0.85 |
| 3 | Variable | 0.65 |
| 4 | Half clear | 0.50 |
| 5 | Cloudy | 0.30 |
| 6 | Overcast | 0.10 |
| 7+ | Fog / rain / snow | 0.05 |

**Peak Sun Hours** vary by Swedish latitude and season (lookup table embedded in code).

---

## 6. MCP Tools — Specification

### Tool 1: `get_solar_growth`
```
Input:  municipality_name (str)
Output: JSON with historical capacity, YoY growth %, CAGR
```
*"Karlskrona grew solar capacity by 34% in 2023, with a 5-year CAGR of 28%."*

### Tool 2: `compare_generation_forecast`
```
Input:  municipality_name (str), days_ahead (int, default=7)
Output: JSON with forecast kWh, clear-sky kWh, delta (absolute + %)
```
*"Over the next 7 days, Karlskrona is forecast to generate 410 MWh. Under clear skies it would generate 820 MWh — clouds are reducing potential by 50%."*

### Tool 3: `find_optimal_solar_region`
```
Input:  days_ahead (int, default=7)
Output: JSON ranking regions by (a) sunniest, (b) most generation
```
*"Gotland will be sunniest, but Malmö will generate 3× more raw power due to its 8× larger installed base."*

---

## 7. Project File Structure

```
solar-sweden-mcp/
├── planning/
│   └── 2026-02-20-project-plan.md        ← this file
├── data/
│   ├── raw/                               ← downloaded Energimyndigheten Excel files
│   └── processed/                         ← Parquet files for fast loading
├── src/
│   └── solar_mcp/
│       ├── __init__.py
│       ├── server.py                      ← FastAPI + MCP server entry point
│       ├── tools/
│       │   ├── solar_growth.py
│       │   ├── generation_forecast.py
│       │   └── optimal_region.py
│       ├── data/
│       │   ├── energimyndigheten.py       ← data loader + sample fallback
│       │   └── smhi_client.py             ← SMHI API client + TTL cache
│       └── utils/
│           ├── municipality_coords.py
│           └── solar_formula.py
├── presentation/
│   └── solar-sweden-mcp.qmd              ← Quarto slide deck
├── notebooks/
│   └── 01-data-exploration.ipynb
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── requirements.txt
└── README.md
```

---

## 8. Deployment on Azure

- **Service:** Azure Container Apps (scale to zero when idle)
- **Image:** Multi-stage Docker build, Python 3.12 slim base
- **Config:** Environment variables for any secrets (no secrets needed for free SMHI)
- **MCP Endpoint:** `POST /mcp` (Streamable HTTP) and `GET /sse` (SSE fallback)
- **Health check:** `GET /health`

---

## 9. Copilot Studio Integration

1. Open Copilot Studio → *Topics → Add action → MCP*
2. Register server URL: `https://<app>.azurecontainerapps.io/sse`
3. Copilot Studio auto-discovers the three tools via MCP tool listing
4. Build natural-language topics that call each tool

---

## 10. Iteration Roadmap

| Phase | Scope | Status |
|-------|-------|--------|
| 0 | Project skeleton, planning doc | ✅ Done |
| 1 | Data loading (static + API), formula utils | ✅ Done |
| 2 | Three MCP tools implemented | ✅ Done |
| 3 | FastAPI + MCP server wired up | ✅ Done |
| 4 | Docker build & Azure deploy | ✅ Done (scripts in `deploy/`) |
| 5 | Quarto presentation | ✅ Done |
| 6 | Copilot Studio integration test | ⬜ Pending |
| 7 | Polish & live demo rehearsal | ⬜ Pending |

---

## 11. Open Questions / Next Steps

- [ ] Download actual Energimyndigheten Excel files and run `scripts/process_solar_data.py` to generate Parquet
- [x] Validate SMHI API parameter names against a live API response — confirmed: `t`, `Wsymb2`, `lcc_mean`, `mcc_mean`, `hcc_mean` all present; forecast spans ~9.5 days at mixed 1h/6h/12h intervals
- [ ] Confirm whether Copilot Studio uses SSE or Streamable HTTP — test both
- [ ] Decide on Azure Container App tier for demo day (min 1 replica to avoid cold start)
- [ ] Add authentication layer if demo requires private endpoint
