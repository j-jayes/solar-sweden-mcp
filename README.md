# Solar Sweden MCP

**AI-powered solar generation forecasting for Microsoft Copilot Studio**

An MCP (Model Context Protocol) server that combines Swedish solar panel installation data with live SMHI weather forecasts, enabling Microsoft Copilot Studio to answer natural-language questions about solar energy production across Sweden.

---

## Live Deployment

| Endpoint | URL |
|----------|-----|
| **MCP (Streamable HTTP)** | `https://solar-mcp.thankfulglacier-f4abeca6.swedencentral.azurecontainerapps.io/mcp` |
| MCP (SSE fallback) | `https://solar-mcp.thankfulglacier-f4abeca6.swedencentral.azurecontainerapps.io/sse` |
| Health check | `https://solar-mcp.thankfulglacier-f4abeca6.swedencentral.azurecontainerapps.io/health` |

**Copilot Studio setup:** Topics → Add action → MCP → paste the `/mcp` URL above → all 8 tools are auto-discovered.

---

## What can you ask?

| Question | Tool |
|----------|------|
| *"How fast has solar grown in Karlskrona?"* | `get_solar_growth` |
| *"Which municipality is growing the fastest?"* | `get_fastest_growth` |
| *"How much power will clouds cost us this week?"* | `compare_generation_forecast` |
| *"Which region will generate the most solar power next week?"* | `find_optimal_solar_region` |
| *"Show me a map of solar capacity across Sweden"* | `get_solar_map` |
| *"What are the electricity spot prices in SE3 tomorrow?"* | `get_electricity_prices` |
| *"Which municipalities are on the border of SE3 and SE4?"* | `list_zone_border_municipalities` |
| *"How much is Karlskrona's solar production worth today?"* | `estimate_solar_revenue` |

---

## Tools

### Historical Solar Data (Energimyndigheten)
- **`get_solar_growth`**: Returns historical capacity growth for any Swedish municipality: year-over-year percentages and CAGR since 2016.
- **`get_fastest_growth`**: Ranks all municipalities by the fastest growth rate in solar panel installations between two given years.
- **`get_solar_map`**: Returns a choropleth PNG map of Sweden coloured by installed solar capacity (kW) by municipality, plus a JSON summary with national totals and the top 10 municipalities.

### Weather & Generation Forecasts (SMHI)
- **`compare_generation_forecast`**: Compares expected generation over the coming days against a perfect clear-sky scenario, showing the cloud-cover penalty in kWh and percentage.
- **`find_optimal_solar_region`**: Ranks 15 municipalities by (1) sunniest forecast and (2) highest expected generation.

### Electricity Prices (Nord Pool)
- **`get_electricity_prices`**: Returns Nord Pool day-ahead electricity spot prices for the four Swedish pricing zones (SE1–SE4).
- **`list_zone_border_municipalities`**: Lists municipalities that sit on the border between electricity pricing zones, useful for cross-border price comparisons.

### Combined Analysis
- **`estimate_solar_revenue`**: Combines SMHI weather forecasts, installed solar capacity, and Nord Pool electricity spot prices to estimate the financial value of a municipality's solar generation for a specific day.

---

## Data Sources

- **[Energimyndigheten](https://www.energimyndigheten.se/statistik/officiell-energistatistik/tillforsel-och-anvandning/natanslutna-solcellsanlaggningar/)** — 290 municipalities × 9 years (2016–2024), downloaded via PxWeb API and cached as Parquet. National capacity grew from **134 MW → 4,808 MW** over this period.
- **[SMHI Open Data](https://opendata.smhi.se/apidocs/metfcst/index.html)** — free 9-day point weather forecast (CC BY 4.0). Clearness is derived from weighted cloud-layer cover (lcc/mcc/hcc), not just the weather symbol.
- **[Nord Pool via mgrey.se](https://mgrey.se)** — day-ahead electricity spot prices (SE1-SE4). Tomorrow's prices are typically available after 13:00 CET.
- **[okfse/sweden-geojson](https://github.com/okfse/sweden-geojson)** — 290-feature GeoJSON for choropleth maps.

---

## Copilot Studio Agent Setup

### 1. Create or open an agent

Go to [Copilot Studio](https://copilotstudio.microsoft.com), create a new agent or open an existing one.

### 2. Add the MCP server

Navigate to **Actions** in the left sidebar → **Add an action** → **Model Context Protocol**.

Enter the server URL:
```
https://solar-mcp.thankfulglacier-f4abeca6.swedencentral.azurecontainerapps.io/mcp
```

Copilot Studio will connect and auto-discover all 8 tools. No authentication is required.

### 3. Server description

When prompted for a server name and description, use:

> **Name:** Solar Sweden MCP
>
> **Description:** Provides real-time and historical data about solar panel installations across Swedish municipalities. Use it to answer questions about solar capacity growth, weather-adjusted generation forecasts, Nord Pool electricity prices, regional comparisons, and to generate visual choropleth maps of Sweden's solar infrastructure. Data covers all 290 Swedish municipalities from 2016 to 2024, with live weather from SMHI and spot prices from Nord Pool.

### 4. Agent instructions

Add the following to your agent's **Instructions** field to give it the right context (you can see the full Swedish instructions in `copilot-studio-instructions.md`):

```
Du är Solar Sverige, en specialiserad assistent för solenergidata och 
elmarknadsanalys i Sverige. Svara alltid på svenska.

Du kan svara på frågor om:
- Hastigheten för solcellsutbyggnad i specifika kommuner
- Den förväntade elproduktionen (kWh) för de kommande dagarna
- Elpriser från Nord Pool (SE1-SE4)
- Beräknade intäkter för solenergi i en kommun
- Kartor över solkapaciteten i Sverige

När du visar ett kart-URL från get_solar_map, rendera det alltid som en inbäddad 
bild med markdown-syntaxen ![karta](url). Säg inte "Jag kan inte visa bilder" - 
bilden är en renderad PNG som fungerar i chatten.
```

### 5. Test it

Use the **Test** pane in Copilot Studio with these example prompts:

- *"How fast has solar grown in Karlskrona?"*
- *"Which municipality grew the fastest between 2020 and 2024?"*
- *"What will Göteborg generate this week compared to clear-sky conditions?"*
- *"What are the current electricity spot prices in SE3?"*
- *"How much is Malmö's solar expected to earn tomorrow based on the Nord Pool spot price?"*
- *"Which Swedish city will generate the most solar power over the next 7 days?"*
- *"Show me a map of solar capacity across Sweden"*

---

## Quick Start (local)

```bash
# Install dependencies
uv sync

# Download real data (first time only)
uv run python scripts/download_solar_data.py   # → data/processed/solar_installations.parquet
uv run python scripts/download_geo.py          # → data/geo/municipalities.geojson
uv run python -m playwright install chromium   # for get_solar_map screenshots

# Run the server
uv run uvicorn solar_mcp.server:app --reload --port 8000

# Run the tests
uv run pytest tests/ -v    # 44 tests
```

Connect Copilot Studio to `http://localhost:8000/mcp` for local testing.

> **Windows:** if `uv run` fails due to permissions, use `.venv/Scripts/python -m uvicorn ...` instead.

---

## Project Structure

```
solar-sweden-mcp/
├── data/
│   ├── raw/                 ← cached API response (JSON)
│   ├── processed/           ← solar_installations.parquet (290 municipalities)
│   └── geo/                 ← municipalities.geojson (290 features)
├── scripts/
│   ├── download_solar_data.py   ← fetches Energimyndigheten PxWeb API
│   └── download_geo.py          ← downloads Sweden municipality GeoJSON
├── src/solar_mcp/
│   ├── server.py                ← FastAPI + MCP (Streamable HTTP + SSE)
│   ├── tools/
│   │   ├── electricity_prices.py
│   │   ├── generation_forecast.py
│   │   ├── growth_ranking.py
│   │   ├── optimal_region.py
│   │   ├── solar_growth.py
│   │   ├── solar_map.py         ← folium choropleth + Playwright screenshot
│   │   └── solar_revenue.py     ← combined Nord Pool + SMHI analysis
│   ├── data/
│   │   ├── energimyndigheten.py ← parquet loader
│   │   └── smhi_client.py       ← SMHI API client + 30-min TTL cache
│   └── utils/
│       ├── municipality_coords.py
│       └── solar_formula.py     ← cloud-layer clearness, PVGIS PSH table
├── tests/                   ← 44 tests, all passing
├── presentation/            ← Quarto slide deck
├── deploy/
│   ├── azure-deploy.sh      ← first-time deploy
│   └── azure-update.sh      ← redeploy after code changes
└── Dockerfile               ← single-stage, includes Playwright Chromium (~1.2 GB)
```

---

## Deploy to Azure

```bash
# First-time deploy (creates resource group, ACR, Container App)
./deploy/azure-deploy.sh

# Redeploy after code changes
./deploy/azure-update.sh
```

The current deployment runs on **Azure Container Apps** (Sweden Central), 1 CPU / 2 Gi memory, min 1 replica.

---

## See Also

- [Project Plan](planning/2026-02-20-project-plan.md)
- [Quarto Presentation: Deep Dive](presentation/solar-sweden-mcp.qmd)
- [Quarto Presentation: Copilot Architecture](presentation/copilot-studio-mcp-architecture.qmd)
