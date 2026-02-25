"""Solar Sweden MCP Server

Exposes eight MCP tools over two transports:

  • Streamable HTTP  → POST/GET/DELETE /mcp   (Copilot Studio compatible, MCP spec 2025-03)
  • SSE              → GET /sse + POST /messages  (legacy fallback)

Tools
-----
  • get_solar_growth              – historical capacity growth per municipality
  • compare_generation_forecast   – forecast vs clear-sky generation delta
  • find_optimal_solar_region     – sunniest / highest-generation ranking
  • get_solar_map                 – choropleth PNG map of Sweden + JSON summary
  • get_fastest_growth            – municipalities ranked by solar growth rate between two years
  • get_electricity_prices        – Nord Pool day-ahead prices for SE1–SE4 zones
  • list_zone_border_municipalities – municipalities on SE2/SE3 and SE3/SE4 zone borders
  • estimate_solar_revenue        – forecast revenue = clearness × capacity × spot price

Run locally
-----------
    .venv/Scripts/python -m uvicorn solar_mcp.server:app --reload --port 8000

Azure deployment
----------------
    ./deploy/azure-deploy.sh
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import os
from typing import Any

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import ImageContent, TextContent, Tool

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.routing import Route as StarletteRoute

from solar_mcp.tools.solar_growth import get_solar_growth
from solar_mcp.tools.generation_forecast import compare_generation_forecast
from solar_mcp.tools.optimal_region import find_optimal_solar_region
from solar_mcp.tools.solar_map import SolarMapResult, get_cached_png, get_solar_map
from solar_mcp.tools.growth_ranking import get_fastest_growth
from solar_mcp.tools.electricity_prices import get_electricity_prices, list_zone_border_municipalities
from solar_mcp.tools.solar_revenue import estimate_solar_revenue

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Public base URL used to construct image links returned to Copilot Studio.
# Override with SERVER_BASE_URL env var in production; defaults to the live Azure URL.
SERVER_BASE_URL = os.getenv(
    "SERVER_BASE_URL",
    "https://solar-mcp.thankfulglacier-f4abeca6.swedencentral.azurecontainerapps.io",
).rstrip("/")

# ---------------------------------------------------------------------------
# MCP Server instance
# ---------------------------------------------------------------------------
mcp_server = Server("solar-sweden-mcp")


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------
@mcp_server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_solar_growth",
            description=(
                "Returns historical solar panel installation data and growth metrics "
                "for a Swedish municipality. Includes year-over-year percentage growth "
                "and CAGR. "
                "Example: get_solar_growth('Karlskrona')"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "municipality_name": {
                        "type": "string",
                        "description": (
                            "Name of a Swedish municipality, e.g. 'Karlskrona', "
                            "'Malmö', 'Stockholm'."
                        ),
                    }
                },
                "required": ["municipality_name"],
            },
        ),
        Tool(
            name="compare_generation_forecast",
            description=(
                "Compares the expected solar electricity generation for a municipality "
                "over the coming days against what would be generated under perfectly "
                "clear skies. Shows the cloud-cover penalty in kWh and percentage. "
                "Example: compare_generation_forecast('Karlskrona', days_ahead=7)"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "municipality_name": {
                        "type": "string",
                        "description": "Swedish municipality name.",
                    },
                    "days_ahead": {
                        "type": "integer",
                        "description": "Forecast horizon in days (1–9). Default 7.",
                        "default": 7,
                        "minimum": 1,
                        "maximum": 9,
                    },
                },
                "required": ["municipality_name"],
            },
        ),
        Tool(
            name="find_optimal_solar_region",
            description=(
                "Ranks 15 representative Swedish municipalities by two dimensions: "
                "(1) sunniest forecast (clearness index), and "
                "(2) highest expected electricity generation (kWh). "
                "The 15 municipalities are: Karlskrona, Malmö, Göteborg, Stockholm, Lund, "
                "Helsingborg, Uppsala, Linköping, Västerås, Gotland, Örebro, Jönköping, "
                "Varberg, Kalmar, Halmstad. "
                "Reveals whether the sunniest region also generates the most power "
                "(it often does not, because a cloudier city with much more installed capacity "
                "can still out-produce a sunnier but smaller one). "
                "Example: find_optimal_solar_region(days_ahead=7)"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "days_ahead": {
                        "type": "integer",
                        "description": "Forecast horizon in days (1–9). Default 7.",
                        "default": 7,
                        "minimum": 1,
                        "maximum": 9,
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="get_solar_map",
            description=(
                "Generates a choropleth map of Sweden showing installed solar capacity "
                "(kW) by municipality. Returns a JSON summary with the top 10 municipalities "
                "and national totals, plus a map_image_url field linking to a PNG image "
                "of the map. Always display the map_image_url as a markdown image so the "
                "user can see the visual. "
                "Optionally specify a year (2016–2024); defaults to the most recent year. "
                "Example: get_solar_map() or get_solar_map(year=2023)"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "year": {
                        "type": "integer",
                        "description": (
                            "Year for which to display installed capacity (2016–2024). "
                            "Defaults to the most recent year in the dataset."
                        ),
                        "minimum": 2016,
                        "maximum": 2024,
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="get_fastest_growth",
            description=(
                "Returns Swedish municipalities ranked by the fastest growth rate in "
                "solar panel installations between two years. Supports ranking by either "
                "installed capacity (kW) or number of installations. "
                "Use this to answer: 'which municipality had the fastest solar growth between 2018 and 2022?' "
                "Example: get_fastest_growth(start_year=2019, end_year=2023, metric='capacity', top_n=10)"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "start_year": {
                        "type": "integer",
                        "description": "Start year of the comparison window (e.g. 2019). Data available 2016–2024.",
                        "minimum": 2016,
                        "maximum": 2024,
                    },
                    "end_year": {
                        "type": "integer",
                        "description": "End year of the comparison window (e.g. 2023). Must be after start_year.",
                        "minimum": 2016,
                        "maximum": 2024,
                    },
                    "metric": {
                        "type": "string",
                        "description": "'capacity' to rank by installed kW growth (default), or 'installations' to rank by number of installations growth.",
                        "enum": ["capacity", "installations"],
                        "default": "capacity",
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "Number of top municipalities to return (default 10, max 50).",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 50,
                    },
                },
                "required": ["start_year", "end_year"],
            },
        ),
        Tool(
            name="get_electricity_prices",
            description=(
                "Returns Nord Pool day-ahead electricity spot prices for the four Swedish "
                "pricing zones: SE1 (Luleå/Northern), SE2 (Sundsvall/Central-North), "
                "SE3 (Stockholm/Central), SE4 (Malmö/Southern). "
                "Prices are per MWh in SEK or EUR. SE1/SE2 are typically cheaper due to "
                "surplus hydro/wind power; SE3/SE4 are more expensive. "
                "Use this to answer: 'what are today's electricity prices in Sweden?' or "
                "'what will tomorrow's prices be in SE4?' "
                "Example: get_electricity_prices(delivery_date='tomorrow', currency='SEK')"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "delivery_date": {
                        "type": "string",
                        "description": "'today', 'tomorrow', or an ISO date 'YYYY-MM-DD'. Tomorrow's prices are published around 13:00 CET.",
                        "default": "today",
                    },
                    "currency": {
                        "type": "string",
                        "description": "'SEK' (Swedish kronor, default) or 'EUR' (euros). Prices are per MWh.",
                        "enum": ["SEK", "EUR"],
                        "default": "SEK",
                    },
                    "areas": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["SE1", "SE2", "SE3", "SE4"]},
                        "description": "Which SE zones to include. Defaults to all four.",
                    },
                    "include_border_municipalities": {
                        "type": "boolean",
                        "description": "If true, also returns the table of municipalities on zone borders.",
                        "default": False,
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="list_zone_border_municipalities",
            description=(
                "Returns a table of Swedish municipalities that sit on or near an electricity "
                "pricing zone border (SE2/SE3 or SE3/SE4). These municipalities are relevant "
                "for comparing solar revenue across zone boundaries, since customers on either "
                "side of the same street could pay different electricity prices. "
                "Includes the primary zone, adjacent zone, county, and explanatory notes. "
                "Example: list_zone_border_municipalities()"
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="estimate_solar_revenue",
            description=(
                "Estimates the electricity revenue that a municipality's installed solar capacity "
                "would earn on a given day, combining SMHI weather forecasts, installed capacity "
                "data, and Nord Pool day-ahead spot prices. "
                "Returns forecast generation (kWh), average spot price (SEK/MWh), estimated revenue, "
                "and comparison with a clear-sky maximum. For border municipalities, also shows "
                "what the revenue would be in the adjacent pricing zone. "
                "Use this to answer: 'how much would tomorrow's solar generation in Lund sell for?' "
                "or 'compare solar revenue for Varberg (SE3) vs Halmstad (SE4) tomorrow'. "
                "Example: estimate_solar_revenue('Lund', days_ahead=1, currency='SEK')"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "municipality_name": {
                        "type": "string",
                        "description": "Swedish municipality name, e.g. 'Lund', 'Varberg', 'Stockholm'.",
                    },
                    "days_ahead": {
                        "type": "integer",
                        "description": "0 = today, 1 = tomorrow (default), up to 9 days ahead.",
                        "default": 1,
                        "minimum": 0,
                        "maximum": 9,
                    },
                    "currency": {
                        "type": "string",
                        "description": "'SEK' (default) or 'EUR'.",
                        "enum": ["SEK", "EUR"],
                        "default": "SEK",
                    },
                },
                "required": ["municipality_name"],
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Tool call handler
# ---------------------------------------------------------------------------
@mcp_server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent | ImageContent]:
    logger.info("Tool called: %s with args: %s", name, arguments)

    try:
        if name == "get_solar_growth":
            result = get_solar_growth(arguments["municipality_name"])
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

        elif name == "compare_generation_forecast":
            result = await asyncio.to_thread(
                compare_generation_forecast,
                arguments["municipality_name"],
                int(arguments.get("days_ahead", 7)),
            )
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

        elif name == "find_optimal_solar_region":
            result = await asyncio.to_thread(
                find_optimal_solar_region,
                int(arguments.get("days_ahead", 7)),
            )
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

        elif name == "get_solar_map":
            year_arg = arguments.get("year")
            # Run the blocking Playwright screenshot in a thread so we don't
            # block the asyncio event loop (sync_playwright() raises if called
            # from within an event loop).
            map_result: SolarMapResult = await asyncio.to_thread(
                get_solar_map,
                int(year_arg) if year_arg is not None else None,
            )
            # Inject a stable image URL into the summary so Copilot Studio
            # can render the map inline as a markdown image.
            year_used = map_result.summary.get("year")
            if year_used is not None:
                image_url = f"{SERVER_BASE_URL}/maps/{year_used}.png"
                map_result.summary["map_image_url"] = image_url
                map_result.summary["map_image_markdown"] = (
                    f"![Solar Capacity Map of Sweden {year_used}]({image_url})"
                )

            contents: list[TextContent | ImageContent] = [
                TextContent(
                    type="text",
                    text=json.dumps(map_result.summary, ensure_ascii=False, indent=2),
                )
            ]
            if map_result.image_bytes is not None:
                contents.append(
                    ImageContent(
                        type="image",
                        data=base64.b64encode(map_result.image_bytes).decode("ascii"),
                        mimeType=map_result.mime_type,
                    )
                )
            return contents

        elif name == "get_fastest_growth":
            result = get_fastest_growth(
                start_year=int(arguments["start_year"]),
                end_year=int(arguments["end_year"]),
                metric=arguments.get("metric", "capacity"),
                top_n=int(arguments.get("top_n", 10)),
            )
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

        elif name == "get_electricity_prices":
            result = await asyncio.to_thread(
                get_electricity_prices,
                arguments.get("delivery_date", "today"),
                arguments.get("currency", "SEK"),
                arguments.get("areas") or None,
                bool(arguments.get("include_border_municipalities", False)),
            )
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

        elif name == "list_zone_border_municipalities":
            result = list_zone_border_municipalities()
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

        elif name == "estimate_solar_revenue":
            result = await asyncio.to_thread(
                estimate_solar_revenue,
                arguments["municipality_name"],
                int(arguments.get("days_ahead", 1)),
                arguments.get("currency", "SEK"),
            )
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

        else:
            result = {"error": f"Unknown tool: {name}"}
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    except Exception as exc:  # noqa: BLE001
        logger.exception("Error in tool %s", name)
        result = {"error": str(exc)}
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


# ---------------------------------------------------------------------------
# Transports
# ---------------------------------------------------------------------------

# Streamable HTTP — Copilot Studio uses this (MCP spec 2025-03-26)
_session_manager = StreamableHTTPSessionManager(
    app=mcp_server,
    stateless=True,  # stateless: each request is independent, no persistent session needed
)

# SSE — legacy fallback for older MCP clients
_sse_transport = SseServerTransport("/messages")


class _MCPStreamableHTTPApp:
    """Thin ASGI wrapper that routes requests into the StreamableHTTP session manager.

    Mounted via app.mount() so FastAPI never wraps the response — the session
    manager writes directly to the ASGI send callable, which is the correct
    pattern for MCP Streamable HTTP (GET/POST/DELETE on the same endpoint).
    """

    async def __call__(self, scope, receive, send) -> None:
        await _session_manager.handle_request(scope, receive, send)


# ---------------------------------------------------------------------------
# FastAPI lifespan: start/stop the Streamable HTTP session manager
# ---------------------------------------------------------------------------
@contextlib.asynccontextmanager
async def _lifespan(app: FastAPI):
    async with _session_manager.run():
        logger.info("StreamableHTTP session manager started")
        yield
    logger.info("StreamableHTTP session manager stopped")


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Solar Sweden MCP",
    description="MCP server exposing Swedish solar panel statistics and weather forecasts.",
    version="0.1.0",
    lifespan=_lifespan,
)

# ---------------------------------------------------------------------------
# Streamable HTTP endpoint (Copilot Studio)
#
# Two registrations keep both /mcp and /mcp/ working without redirects:
#
#   1. StarletteRoute("/mcp", ...)  — exact match, no redirect, inserted first
#   2. app.mount("/mcp", ...)       — prefix match for /mcp/ and deeper paths
#
# The session manager writes the ASGI response directly, bypassing FastAPI's
# response wrapping. Handles GET / POST / DELETE on the same endpoint.
# Register https://<host>/mcp in Copilot Studio as the MCP server URL.
# ---------------------------------------------------------------------------
_mcp_asgi_app = _MCPStreamableHTTPApp()

# Exact-path route for /mcp — inserted at position 0 so it is checked before
# any Mount that would otherwise generate a 307 redirect.
app.router.routes.insert(0, StarletteRoute("/mcp", endpoint=_mcp_asgi_app))

# Prefix mount for /mcp/ (and deeper paths, e.g. future versioned endpoints)
app.mount("/mcp", _mcp_asgi_app)


# ---------------------------------------------------------------------------
# Map image endpoint
#
# Serves the choropleth PNG for a given year. Returns the cached bytes if
# get_solar_map() was already called this process lifetime; otherwise
# generates the map on demand (takes ~5 s due to Playwright).
#
# This URL is included in the get_solar_map tool response as map_image_url
# so Copilot Studio (which does not render MCP ImageContent) can display
# the image by rendering the URL as a markdown image.
# ---------------------------------------------------------------------------
@app.get("/maps/{year}.png", response_class=Response)
async def map_image(year: int):
    """Serve the solar capacity choropleth PNG for the given year."""
    png = get_cached_png(year)
    if png is None:
        # Not yet cached — generate it in a thread (sync_playwright() must not
        # run inside an asyncio event loop; ~5 s on first call).
        result = await asyncio.to_thread(get_solar_map, year)
        png = result.image_bytes
    if png is None:
        return JSONResponse({"error": "Map generation failed"}, status_code=500)
    return Response(content=png, media_type="image/png")


# ---------------------------------------------------------------------------
# Legacy SSE endpoints (backward-compatible fallback)
# ---------------------------------------------------------------------------
@app.get("/sse")
async def sse_endpoint(request: Request):
    """SSE endpoint — legacy fallback for older MCP clients."""
    async with _sse_transport.connect_sse(
        request.scope, request.receive, request._send  # noqa: SLF001
    ) as streams:
        await mcp_server.run(
            streams[0],
            streams[1],
            mcp_server.create_initialization_options(),
        )


@app.post("/messages")
async def messages_endpoint(request: Request):
    """SSE POST handler for legacy clients."""
    await _sse_transport.handle_post_message(
        request.scope, request.receive, request._send  # noqa: SLF001
    )


# ---------------------------------------------------------------------------
# Health / info endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
async def health_check():
    """Health check endpoint for Azure Container Apps."""
    return JSONResponse({"status": "ok", "service": "solar-sweden-mcp"})


@app.get("/")
async def root():
    """API root — returns service info and available endpoints."""
    return JSONResponse(
        {
            "service": "Solar Sweden MCP",
            "description": "MCP server for Swedish solar generation forecasting",
            "mcp_streamable_http_endpoint": "/mcp",
            "mcp_sse_endpoint": "/sse",
            "health_endpoint": "/health",
            "map_image_endpoint": "/maps/{year}.png",
            "tools": [
                "get_solar_growth",
                "compare_generation_forecast",
                "find_optimal_solar_region",
                "get_solar_map",
                "get_fastest_growth",
                "get_electricity_prices",
                "list_zone_border_municipalities",
                "estimate_solar_revenue",
            ],
        }
    )
