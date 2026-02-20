# Solar Sweden MCP

**AI-powered solar generation forecasting for Affärsverken, Karlskrona**

An MCP (Model Context Protocol) server that combines Swedish solar panel installation data with live SMHI weather forecasts, enabling Microsoft Copilot Studio to answer natural-language questions about solar energy production across Sweden.

---

## What can you ask?

| Question | Tool |
|---|---|
| *"How fast has solar grown in Karlskrona?"* | `get_solar_growth` |
| *"How much power will clouds cost us this week?"* | `compare_generation_forecast` |
| *"Which region will generate the most solar power?"* | `find_optimal_solar_region` |

---

## Data Sources

- **[Energimyndigheten](https://www.energimyndigheten.se/statistik/officiell-energistatistik/tillforsel-och-anvandning/natanslutna-solcellsanlaggningar/)** — annual statistics on grid-connected solar installations per municipality (static, 2019–2024)
- **[SMHI Open Data](https://opendata.smhi.se/apidocs/metfcst/index.html)** — free 10-day point weather forecast API (live, CC BY 4.0)

---

## Quick Start

```bash
# Install dependencies
pip install -e ".[dev]"

# Run the MCP server locally
uvicorn solar_mcp.server:app --reload --port 8000

# Test with a browser
open http://localhost:8000/
```

Connect Copilot Studio to `http://localhost:8000/sse`.

---

## Project Structure

```
solar-sweden-mcp/
├── planning/           ← project plan
├── data/raw/           ← put Energimyndigheten .xlsx files here
├── src/solar_mcp/      ← Python package
│   ├── server.py       ← FastAPI + MCP server
│   ├── tools/          ← the three MCP tools
│   ├── data/           ← data loaders + SMHI client
│   └── utils/          ← coords, solar formula
├── tests/              ← pytest suite (28 tests)
├── presentation/       ← Quarto slide deck
└── Dockerfile          ← Azure Container Apps
```

---

## Deploy to Azure

```bash
# Build and push
az acr build --registry <YOUR_ACR> --image solar-mcp:latest .

# Deploy
az containerapp create \
  --name solar-mcp \
  --resource-group <RG> \
  --image <YOUR_ACR>.azurecr.io/solar-mcp:latest \
  --ingress external --target-port 8000
```

Then register the `/sse` endpoint as an MCP action in Copilot Studio.

---

## Run Tests

```bash
pytest tests/ -v
```

---

## See Also

- [Project Plan](planning/2026-02-20-project-plan.md)
- [Quarto Presentation](presentation/solar-sweden-mcp.qmd)
