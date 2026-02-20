"""Solar Sweden MCP Server

Exposes three MCP tools over HTTP (Streamable HTTP + SSE fallback) for use
with Microsoft Copilot Studio:

  • get_solar_growth           – historical capacity growth per municipality
  • compare_generation_forecast – forecast vs clear-sky generation delta
  • find_optimal_solar_region  – sunniest / highest-generation ranking

Transport
---------
The MCP Python SDK (mcp>=1.0) is used with:
  • SseServerTransport  → GET /sse  (Server-Sent Events — Copilot Studio compatible)
  • Streamable HTTP     → POST /messages  (newer MCP spec)

Both endpoints are mounted onto a FastAPI application so the service can also
expose a health check and (optionally) a REST probe endpoint.

Run locally
-----------
    uvicorn solar_mcp.server:app --reload --port 8000

Azure deployment
----------------
See Dockerfile in the project root.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import TextContent, Tool

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.routing import Route

from solar_mcp.tools.solar_growth import get_solar_growth
from solar_mcp.tools.generation_forecast import compare_generation_forecast
from solar_mcp.tools.optimal_region import find_optimal_solar_region

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
                        "description": "Forecast horizon in days (1–10). Default 7.",
                        "default": 7,
                        "minimum": 1,
                        "maximum": 10,
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
                        "description": "Forecast horizon in days (1–10). Default 7.",
                        "default": 7,
                        "minimum": 1,
                        "maximum": 10,
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
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    logger.info("Tool called: %s with args: %s", name, arguments)

    try:
        if name == "get_solar_growth":
            result = get_solar_growth(arguments["municipality_name"])
        elif name == "compare_generation_forecast":
            result = compare_generation_forecast(
                municipality_name=arguments["municipality_name"],
                days_ahead=int(arguments.get("days_ahead", 7)),
            )
        elif name == "find_optimal_solar_region":
            result = find_optimal_solar_region(
                days_ahead=int(arguments.get("days_ahead", 7)),
            )
        else:
            result = {"error": f"Unknown tool: {name}"}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error in tool %s", name)
        result = {"error": str(exc)}

    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Solar Sweden MCP",
    description="MCP server exposing Swedish solar panel statistics and weather forecasts.",
    version="0.1.0",
)

sse_transport = SseServerTransport("/messages")


@app.get("/sse")
async def sse_endpoint(request: Request):
    """SSE endpoint — Copilot Studio connects here."""
    # request._send is the ASGI send callable; accessing it is the documented
    # pattern for the mcp SseServerTransport FastAPI integration.
    async with sse_transport.connect_sse(
        request.scope, request.receive, request._send  # noqa: SLF001
    ) as streams:
        await mcp_server.run(
            streams[0],
            streams[1],
            mcp_server.create_initialization_options(),
        )


@app.post("/messages")
async def messages_endpoint(request: Request):
    """Streamable HTTP endpoint for newer MCP clients."""
    # Same reasoning as above — mcp SDK requires the raw ASGI send callable.
    await sse_transport.handle_post_message(
        request.scope, request.receive, request._send  # noqa: SLF001
    )


@app.get("/health")
async def health_check():
    """Health check endpoint for Azure Container Apps."""
    return JSONResponse({"status": "ok", "service": "solar-sweden-mcp"})


@app.get("/")
async def root():
    """API root — returns service info and available tools."""
    return JSONResponse(
        {
            "service": "Solar Sweden MCP",
            "description": "MCP server for Swedish solar generation forecasting",
            "mcp_sse_endpoint": "/sse",
            "mcp_http_endpoint": "/messages",
            "health_endpoint": "/health",
            "tools": [
                "get_solar_growth",
                "compare_generation_forecast",
                "find_optimal_solar_region",
            ],
        }
    )
