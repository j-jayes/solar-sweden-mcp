"""Solar Sweden MCP Server

Exposes three MCP tools over two transports:

  • Streamable HTTP  → POST/GET/DELETE /mcp   (Copilot Studio compatible, MCP spec 2025-03)
  • SSE              → GET /sse + POST /messages  (legacy fallback)

Tools
-----
  • get_solar_growth           – historical capacity growth per municipality
  • compare_generation_forecast – forecast vs clear-sky generation delta
  • find_optimal_solar_region  – sunniest / highest-generation ranking

Run locally
-----------
    .venv/Scripts/python -m uvicorn solar_mcp.server:app --reload --port 8000

Azure deployment
----------------
    ./deploy/azure-deploy.sh
"""

from __future__ import annotations

import base64
import contextlib
import json
import logging
from typing import Any

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import ImageContent, TextContent, Tool

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.routing import Route as StarletteRoute

from solar_mcp.tools.solar_growth import get_solar_growth
from solar_mcp.tools.generation_forecast import compare_generation_forecast
from solar_mcp.tools.optimal_region import find_optimal_solar_region
from solar_mcp.tools.solar_map import SolarMapResult, get_solar_map

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

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
                "Ranks Swedish municipalities by two dimensions: (1) sunniest forecast, "
                "(2) highest expected electricity generation. Reveals whether the sunniest "
                "region also generates the most power (it might not, if a cloudier region "
                "has much more installed capacity). "
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
                "(kW) by municipality as a PNG image. Also returns a JSON summary with "
                "the top 10 municipalities and national totals. "
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
            result = compare_generation_forecast(
                municipality_name=arguments["municipality_name"],
                days_ahead=int(arguments.get("days_ahead", 7)),
            )
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

        elif name == "find_optimal_solar_region":
            result = find_optimal_solar_region(
                days_ahead=int(arguments.get("days_ahead", 7)),
            )
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

        elif name == "get_solar_map":
            year_arg = arguments.get("year")
            map_result: SolarMapResult = get_solar_map(
                year=int(year_arg) if year_arg is not None else None,
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
            "tools": [
                "get_solar_growth",
                "compare_generation_forecast",
                "find_optimal_solar_region",
                "get_solar_map",
            ],
        }
    )
