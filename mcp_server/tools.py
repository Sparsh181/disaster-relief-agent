"""
MCP Server — Tool Definitions
------------------------------
Exposes three core tools via the Model Context Protocol:

  1. get_disaster_alerts  — fetches live GDACS alerts
  2. get_weather          — fetches Open-Meteo weather
  3. get_full_briefing    — runs full pipeline for an event

Security features:
  - Rate limiting on all tools (via RateLimiter)
  - Input validation on all parameters
  - Prompt injection guard (data treated as data, not instructions)
  - Graceful error handling (never leaks stack traces to callers)
"""

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.trigger_ingestion_agent   import TriggerIngestionAgent
from agents.weather_context_agent     import WeatherContextAgent
from agents.humanitarian_impact_agent import HumanitarianImpactAgent
from agents.synthesis_output_agent    import SynthesisOutputAgent
from agents.risk_reviewer_agent       import RiskReviewerAgent
from mcp_server.rate_limiter          import rate_limiter, rate_limited

VALID_SEVERITIES  = ["Green", "Orange", "Red"]
VALID_EVENT_TYPES = ["ALL", "EQ", "TC", "FL", "VO", "WF", "DR"]


@rate_limited("get_disaster_alerts")
def get_disaster_alerts(
    min_severity: str = "Green",
    event_type: str = "ALL",
    max_results: int = 10
) -> str:
    """
    Fetches the latest global disaster alerts from GDACS.
    Args:
        min_severity : Green, Orange, Red
        event_type   : ALL, EQ, TC, FL, VO, WF, DR
        max_results  : Max alerts to return (1-20)
    Returns: JSON string with alerts list, count, fetch timestamp
    """
    try:
        if min_severity not in VALID_SEVERITIES:
            return json.dumps({"error": f"Invalid min_severity '{min_severity}'. Must be: {VALID_SEVERITIES}"})
        if event_type not in VALID_EVENT_TYPES:
            return json.dumps({"error": f"Invalid event_type '{event_type}'. Must be: {VALID_EVENT_TYPES}"})
        max_results = max(1, min(20, int(max_results)))

        agent  = TriggerIngestionAgent(min_alert_level=min_severity, max_results=max_results)
        alerts = agent.fetch_by_type(event_type) if event_type != "ALL" else agent.fetch()

        return json.dumps({
            "alerts"    : alerts,
            "count"     : len(alerts),
            "fetched_at": datetime.utcnow().isoformat(),
            "source"    : "GDACS"
        }, default=str)

    except Exception as e:
        return json.dumps({"error": f"Tool error: {type(e).__name__}", "alerts": [], "count": 0,
                           "fetched_at": datetime.utcnow().isoformat()})


@rate_limited("get_weather")
def get_weather(
    lat: float,
    lon: float,
    location_name: str = "",
    forecast_days: int = 3
) -> str:
    """
    Fetches current weather + forecast for a location via Open-Meteo.
    Args:
        lat          : Latitude (-90 to 90)
        lon          : Longitude (-180 to 180)
        location_name: Optional display name
        forecast_days: Days of forecast (1-7)
    Returns: JSON string with current conditions, forecast, danger flags
    """
    try:
        lat = float(lat)
        lon = float(lon)

        if not (-90 <= lat <= 90):
            return json.dumps({"error": f"Invalid latitude {lat}. Must be -90 to 90.", "data_available": False})
        if not (-180 <= lon <= 180):
            return json.dumps({"error": f"Invalid longitude {lon}. Must be -180 to 180.", "data_available": False})

        forecast_days = max(1, min(7, int(forecast_days)))

        # Sanitize location_name — treat as data, not instructions
        location_name = str(location_name)[:100].replace("\n", " ").replace("\r", " ")

        agent  = WeatherContextAgent()
        result = agent.fetch(lat, lon, location_name)
        result["source"]     = "Open-Meteo"
        result["fetched_at"] = datetime.utcnow().isoformat()
        result["location"]   = {"lat": lat, "lon": lon, "name": location_name}

        return json.dumps(result, default=str)

    except ValueError as e:
        return json.dumps({"error": f"Invalid input: {str(e)}", "data_available": False})
    except Exception as e:
        return json.dumps({"error": f"Tool error: {type(e).__name__}", "data_available": False,
                           "current": {}, "forecast": [], "danger_flags": []})


@rate_limited("get_full_briefing")
def get_full_briefing(
    event_id: int,
    event_type: str,
    include_impact: bool = True
) -> str:
    """
    Runs the complete disaster relief pipeline for a GDACS event.
    Args:
        event_id      : GDACS event ID (int)
        event_type    : EQ, TC, FL, VO, WF, DR
        include_impact: Include LLM assessment (False = faster, no quota)
    Returns: JSON string with briefing_text, structured data, review report
    """
    try:
        event_id   = int(event_id)
        event_type = str(event_type).upper().strip()

        if event_type not in [t for t in VALID_EVENT_TYPES if t != "ALL"]:
            return json.dumps({"error": f"Invalid event_type '{event_type}'."})
        if event_id <= 0:
            return json.dumps({"error": f"Invalid event_id {event_id}."})

        trigger = TriggerIngestionAgent(min_alert_level="Green", max_results=20)
        alerts  = trigger.fetch()
        alert   = next((a for a in alerts
                        if a.get("event_id") == event_id
                        and a.get("event_type") == event_type), None)

        if not alert:
            return json.dumps({"error": f"Event {event_type}:{event_id} not found in GDACS feed.",
                               "event_id": event_id})

        weather = WeatherContextAgent().fetch_for_alert(alert)

        if include_impact:
            impact = HumanitarianImpactAgent().assess(alert, weather)
        else:
            impact = {
                "overall_severity": alert.get("alert_level","").lower(),
                "confidence": "low", "reasoning": "LLM skipped", "llm_available": False,
                "population_at_risk": {"summary": "Assessment skipped", "vulnerability_factors": [], "estimated_scale": "unknown"},
                "infrastructure_threats": {"summary": "Assessment skipped", "specific_risks": []},
                "immediate_dangers": {"summary": "Assessment skipped", "danger_list": [], "time_sensitivity": "unknown"},
                "recommended_actions": {"for_residents": ["Follow official local guidance"], "for_responders": ["Await official assessment"]}
            }

        briefing = SynthesisOutputAgent().synthesize(alert, weather, impact)
        reviewed = RiskReviewerAgent().review(briefing)

        return json.dumps({
            "briefing_text"  : reviewed["text"],
            "structured"     : reviewed["structured"],
            "review_report"  : reviewed["review_report"],
            "pipeline_stages": reviewed["metadata"]["pipeline_stages"] + ["risk_reviewer"],
            "event_id"       : event_id,
            "generated_at"   : datetime.utcnow().isoformat()
        }, default=str)

    except Exception as e:
        return json.dumps({"error": f"Tool error: {type(e).__name__}", "event_id": event_id,
                           "generated_at": datetime.utcnow().isoformat()})


TOOLS = {
    "get_disaster_alerts": get_disaster_alerts,
    "get_weather"        : get_weather,
    "get_full_briefing"  : get_full_briefing,
}