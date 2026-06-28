"""
MCP Server — Disaster Relief Agent
------------------------------------
Exposes disaster relief tools via Model Context Protocol.

Usage:
  python mcp_server/server.py --test    # test tools without starting server
  python mcp_server/server.py --http    # HTTP server on port 8080
  python mcp_server/server.py           # stdio mode for ADK integration
"""

import json
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server.fastmcp import FastMCP
from mcp_server.tools import get_disaster_alerts, get_weather, get_full_briefing

# Single-arg init — MCP 1.28.1 only accepts name
mcp = FastMCP("disaster-relief-agent")


@mcp.tool()
def get_disaster_alerts_tool(
    min_severity: str = "Green",
    event_type: str = "ALL",
    max_results: int = 10
) -> str:
    """
    Fetch latest global disaster alerts from GDACS
    (Global Disaster Alert and Coordination System).
    Args:
        min_severity: Minimum alert level — Green, Orange, or Red
        event_type  : Filter by type — ALL, EQ, TC, FL, VO, WF, DR
        max_results : Maximum alerts to return (1-20)
    Returns:
        JSON string with alerts list, count, and fetch timestamp
    """
    return get_disaster_alerts(min_severity, event_type, max_results)


@mcp.tool()
def get_weather_tool(
    lat: float,
    lon: float,
    location_name: str = "",
    forecast_days: int = 3
) -> str:
    """
    Fetch current weather and forecast for a location via Open-Meteo.
    Args:
        lat          : Latitude (-90 to 90)
        lon          : Longitude (-180 to 180)
        location_name: Optional display name
        forecast_days: Days of forecast (1-7)
    Returns:
        JSON string with current conditions, forecast, and danger flags
    """
    return get_weather(lat, lon, location_name, forecast_days)


@mcp.tool()
def get_full_briefing_tool(
    event_id: int,
    event_type: str,
    include_impact: bool = True
) -> str:
    """
    Run the complete disaster relief pipeline for a GDACS event.
    Fetches alert, weather, runs LLM impact assessment, and
    returns a reviewed plain-language humanitarian briefing.
    Args:
        event_id      : GDACS event ID (from get_disaster_alerts_tool)
        event_type    : Event type — EQ, TC, FL, VO, WF, DR
        include_impact: Include LLM assessment (False = sensor data only)
    Returns:
        JSON string with briefing_text, structured data, review report
    """
    return get_full_briefing(event_id, event_type, include_impact)


def run_tests():
    """Test all tools directly without starting the server."""
    print("\n" + "="*60)
    print("  MCP SERVER — TOOL TESTS")
    print("="*60)

    # Test 1: get_disaster_alerts Orange+
    print("\n[TEST 1] get_disaster_alerts(min_severity='Orange')")
    result = get_disaster_alerts(min_severity="Orange", max_results=5)
    data   = json.loads(result)
    print(f"  Status : {'✅ OK' if 'error' not in data else '❌ ' + data.get('error','')}")
    print(f"  Count  : {data.get('count', 0)} alerts")
    if data.get("alerts"):
        top = data["alerts"][0]
        print(f"  Top    : {top.get('name')} | {top.get('alert_level')}")

    # Test 2: get_disaster_alerts TC only
    print("\n[TEST 2] get_disaster_alerts(event_type='TC')")
    result = get_disaster_alerts(min_severity="Green", event_type="TC", max_results=3)
    data   = json.loads(result)
    print(f"  Status : {'✅ OK' if 'error' not in data else '❌ ' + data.get('error','')}")
    print(f"  Count  : {data.get('count', 0)} TC alerts")

    # Test 3: get_weather valid location
    print("\n[TEST 3] get_weather(lat=17.5, lon=127.8, 'Japan')")
    result = get_weather(17.5, 127.8, "Japan (Typhoon Area)")
    data   = json.loads(result)
    print(f"  Status : {'✅ OK' if data.get('data_available') else '❌ No data'}")
    if data.get("current"):
        c = data["current"]
        print(f"  Temp   : {c.get('temp_c')}°C | Wind: {c.get('wind_kmh')} km/h | {c.get('condition')}")
    if data.get("danger_flags"):
        print(f"  Flags  : {data['danger_flags']}")

    # Test 4: get_weather invalid input validation
    print("\n[TEST 4] get_weather(lat=999) — invalid input check")
    result = get_weather(999, 0)
    data   = json.loads(result)
    print(f"  Status : {'✅ Caught correctly' if 'error' in data else '❌ Should have errored'}")
    print(f"  Error  : {data.get('error')}")

    # Test 5: get_full_briefing live event (no LLM)
    print("\n[TEST 5] get_full_briefing — live top alert (LLM skipped)")
    from agents.trigger_ingestion_agent import TriggerIngestionAgent
    trigger = TriggerIngestionAgent(min_alert_level="Green", max_results=5)
    top     = trigger.fetch_top()
    if top:
        result = get_full_briefing(
            event_id      = top["event_id"],
            event_type    = top["event_type"],
            include_impact= False
        )
        data = json.loads(result)
        print(f"  Status : {'✅ OK' if 'error' not in data else '❌ ' + str(data.get('error'))}")
        if "briefing_text" in data:
            print(f"\n  BRIEFING PREVIEW:\n")
            print(data["briefing_text"][:600] + "...")
    else:
        print("  No live alerts found")

    print("\n" + "="*60)
    print("  ALL TESTS COMPLETE")
    print("="*60 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Disaster Relief Agent MCP Server")
    parser.add_argument("--test", action="store_true", help="Run tool tests")
    parser.add_argument("--http", action="store_true", help="Run as HTTP server")
    parser.add_argument("--port", type=int, default=8080, help="HTTP port (default: 8080)")
    args = parser.parse_args()

    if args.test:
        run_tests()
    elif args.http:
        print(f"Starting MCP HTTP server on port {args.port}...")
        mcp.run(transport="streamable-http", port=args.port)
    else:
        print("Starting MCP stdio server...", file=sys.stderr)
        mcp.run(transport="stdio")