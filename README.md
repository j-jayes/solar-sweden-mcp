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

**Copilot Studio setup:** Topics → Add action → MCP → paste the `/mcp` URL above → all 4 tools are auto-discovered.

---

## What can you ask?

| Question | Tool |
|----------|------|
| *"How fast has solar grown in Karlskrona?"* | `get_solar_growth` |
| *"How much power will clouds cost us this week?"* | `compare_generation_forecast` |
| *"Which region will generate the most solar power next week?"* | `find_optimal_solar_region` |
| *"Show me a map of solar capacity across Sweden"* | `get_solar_map` |

---

## Tools

### `get_solar_growth`
Returns historical capacity growth for any Swedish municipality: year-over-year percentages and CAGR since 2016.

Example: Karlskrona grew from **1,640 kW** (2016) to **54,810 kW** (2024) — a 55% CAGR.

### `compare_generation_forecast`
Compares expected generation over the coming days against a perfect clear-sky scenario, showing the cloud-cover penalty in kWh and percentage.

### `find_optimal_solar_region`
Ranks 15 municipalities by (1) sunniest forecast and (2) highest expected generation — revealing whether the sunniest region actually generates the most power (it usually doesn't, because capacity dominates).

### `get_solar_map`
Returns a choropleth PNG map of Sweden coloured by installed solar capacity (kW) by municipality, plus a JSON summary with national totals and the top 10 municipalities.

---

## Data Sources

- **[Energimyndigheten](https://www.energimyndigheten.se/statistik/officiell-energistatistik/tillforsel-och-anvandning/natanslutna-solcellsanlaggningar/)** — 290 municipalities × 9 years (2016–2024), downloaded via PxWeb API and cached as Parquet. National capacity grew from **134 MW → 4,808 MW** over this period.
- **[SMHI Open Data](https://opendata.smhi.se/apidocs/metfcst/index.html)** — free 9-day point weather forecast (CC BY 4.0). Clearness is derived from weighted cloud-layer cover (lcc/mcc/hcc), not just the weather symbol.
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

Copilot Studio will connect and auto-discover all 4 tools. No authentication is required.

### 3. Server description

When prompted for a server name and description, use:

> **Name:** Solar Sweden MCP
>
> **Description:** Provides real-time and historical data about solar panel installations across Swedish municipalities. Use it to answer questions about solar capacity growth, weather-adjusted generation forecasts, regional comparisons, and to generate visual choropleth maps of Sweden's solar infrastructure. Data covers all 290 Swedish municipalities from 2016 to 2024, with live 9-day weather forecasts from SMHI.

### 4. Agent instructions

Add the following to your agent's **Instructions** field to give it the right context:

```
You are a Swedish solar energy assistant with access to real data from
Energimyndigheten (Swedish Energy Agency) and live weather forecasts from
SMHI (Swedish Meteorological and Hydrological Institute).

You can answer questions about:
- How solar panel capacity has grown in any Swedish municipality since 2016
- How much electricity a municipality is forecast to generate over the next
  1–9 days, compared to what it would generate under clear skies
- Which municipalities are currently the sunniest, and which will generate
  the most total electricity (these are often different, because a cloudier
  city with much more installed capacity can outproduce a sunnier one)
- A visual map of Sweden showing installed solar capacity by municipality

When a user asks about a municipality, always call the appropriate tool and
present the key numbers clearly. For generation forecasts, emphasise both the
absolute kWh figure and the cloud-loss percentage so the user understands the
weather impact.

When presenting the solar map, always render the image using the
map_image_url field from the JSON response. Output it as a markdown image
on its own line, like this:
![Solar Capacity Map of Sweden 2024](map_image_url_value)
Then summarise the top municipalities and national total from the JSON.
Do not say "I cannot display images" — the map_image_url is a real PNG
served by the MCP server and will render in the chat.

Swedish municipality names with special characters (Malmö, Göteborg, Örebro,
etc.) are handled automatically — you can use the anglicised spelling if needed
(Malmo, Goteborg, Orebro).
```

### 5. Test it

Use the **Test** pane in Copilot Studio with these example prompts:

- *"How fast has solar grown in Karlskrona?"*
- *"What will Göteborg generate this week compared to clear-sky conditions?"*
- *"Which Swedish city will generate the most solar power over the next 7 days?"*
- *"Show me a map of solar capacity across Sweden"*
- *"Is Gotland sunnier than Stockholm right now?"*

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
│   │   ├── solar_growth.py
│   │   ├── generation_forecast.py
│   │   ├── optimal_region.py
│   │   └── solar_map.py         ← folium choropleth + Playwright screenshot
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
- [Quarto Presentation](presentation/solar-sweden-mcp.qmd)
