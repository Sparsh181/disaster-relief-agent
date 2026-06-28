"""
Disaster Relief Agent — ADK Orchestrator (v2)
----------------------------------------------
Wires all 5 agents into a Google ADK SequentialAgent pipeline.

Flow:
  1. TriggerIngestionAgent   → fetches + filters GDACS alerts
  2. WeatherContextAgent     → fetches weather for alert location
  3. HumanitarianImpactAgent → LLM reasons about impact
  4. SynthesisOutputAgent    → assembles plain-language briefing
  5. RiskReviewerAgent       → validates + enforces disclaimer

Key design decisions:
  - gemini-2.0-flash for orchestration LlmAgents (lightweight, tool-calling only)
  - gemini-2.5-flash for HumanitarianImpactAgent only (heavy LLM reasoning)
  - Session state used for inter-agent data passing (avoids JSON escaping issues)
  - Rate limit handling with retry on 429

Usage:
  python agents/orchestrator.py    ← direct Python run
  adk run agents/                  ← ADK CLI (Agent Skills rubric)
  adk web                          ← visual debug UI at localhost:8000
"""

import json
import os
import asyncio
import warnings

# Suppress deprecation warning for SequentialAgent
# (still functional in ADK 2.3.0, removal is future)
warnings.filterwarnings("ignore", category=DeprecationWarning)

from dotenv import load_dotenv
from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import FunctionTool
from google.genai import types

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.trigger_ingestion_agent   import TriggerIngestionAgent
from agents.weather_context_agent     import WeatherContextAgent
from agents.humanitarian_impact_agent import HumanitarianImpactAgent
from agents.synthesis_output_agent    import SynthesisOutputAgent
from agents.risk_reviewer_agent       import RiskReviewerAgent

load_dotenv()

# ── Model config ────────────────────────────────────────────
# gemini-2.0-flash for all orchestration steps (lightweight, tool-calling only)
# gemini-2.5-flash for impact agent only (heavy LLM reasoning)
GEMINI_MODEL  = "gemini-2.5-pro"
IMPACT_MODEL  = "gemini-2.5-pro"


# ══════════════════════════════════════════════════════════
# TOOL FUNCTIONS
# Each wraps one of your existing agent classes.
# ADK calls these when the LlmAgent decides to use the tool.
# Returns plain string (JSON) — ADK stores in session state
# via output_key.
# ══════════════════════════════════════════════════════════

def fetch_disaster_alerts(min_severity: str = "Green") -> str:
    """
    Fetches the latest global disaster alerts from GDACS
    and returns the highest-severity alert as a JSON string.

    Args:
        min_severity: Minimum alert level — Green, Orange, or Red.

    Returns:
        JSON string of the top alert dict.
    """
    try:
        agent = TriggerIngestionAgent(
            min_alert_level=min_severity,
            max_results=5
        )
        top = agent.fetch_top()
        if not top:
            return json.dumps({"error": "No alerts found"})
        return json.dumps(top, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


def fetch_weather_for_location(lat: float, lon: float,
                                country: str = "") -> str:
    """
    Fetches current weather conditions and 3-day forecast
    for a given latitude and longitude.

    Args:
        lat    : Latitude of the disaster location.
        lon    : Longitude of the disaster location.
        country: Country name for logging purposes.

    Returns:
        JSON string of weather context dict.
    """
    try:
        agent  = WeatherContextAgent()
        result = agent.fetch(lat, lon, country)
        return json.dumps(result, default=str)
    except Exception as e:
        return json.dumps({"error": str(e), "data_available": False})


def assess_impact(event_name: str, event_type: str, country: str,
                  alert_level: str, severity_text: str,
                  lat: float, lon: float,
                  current_temp: float, current_wind: float,
                  current_condition: str,
                  forecast_day1: str, forecast_day2: str,
                  forecast_day3: str,
                  danger_flags: str = "") -> str:
    """
    Uses Gemini to assess the humanitarian impact of a disaster
    by reasoning about event data and weather conditions.

    Args:
        event_name       : Name of the disaster event.
        event_type       : Type code — EQ, TC, FL, VO, WF, DR.
        country          : Affected country.
        alert_level      : GDACS alert level — Green/Orange/Red.
        severity_text    : Human-readable severity description.
        lat              : Latitude of the event.
        lon              : Longitude of the event.
        current_temp     : Current temperature in Celsius.
        current_wind     : Current wind speed in km/h.
        current_condition: Current weather condition description.
        forecast_day1    : Day 1 forecast summary string.
        forecast_day2    : Day 2 forecast summary string.
        forecast_day3    : Day 3 forecast summary string.
        danger_flags     : Comma-separated danger flag strings.

    Returns:
        JSON string of impact assessment dict.
    """
    try:
        # Reconstruct alert and weather dicts from flat args
        # (avoids JSON escaping issues in ADK session state passing)
        alert = {
            "event_id"     : None,
            "event_type"   : event_type,
            "name"         : event_name,
            "country"      : country,
            "affected"     : [country],
            "alert_level"  : alert_level,
            "severity_text": severity_text,
            "from_date"    : "",
            "lat"          : lat,
            "lon"          : lon
        }

        weather = {
            "data_available": True,
            "current": {
                "temp_c"   : current_temp,
                "wind_kmh" : current_wind,
                "condition": current_condition
            },
            "forecast": [
                {"date": "Day 1", "summary": forecast_day1},
                {"date": "Day 2", "summary": forecast_day2},
                {"date": "Day 3", "summary": forecast_day3}
            ],
            "danger_flags": (
                [f.strip() for f in danger_flags.split(",")]
                if danger_flags else []
            )
        }

        agent  = HumanitarianImpactAgent()
        result = agent.assess(alert, weather)
        return json.dumps(result, default=str)

    except Exception as e:
        return json.dumps({"error": str(e), "llm_available": False})


def build_briefing(event_name: str, event_type: str, country: str,
                   alert_level: str, severity_text: str,
                   lat: float, lon: float, report_url: str,
                   current_temp: float, current_wind: float,
                   current_condition: str,
                   population_summary: str,
                   infrastructure_summary: str,
                   danger_summary: str,
                   actions_residents: str,
                   overall_severity: str,
                   reasoning: str,
                   confidence: str) -> str:
    """
    Assembles a complete plain-language disaster briefing
    from all upstream pipeline data.

    Args:
        event_name            : Name of the disaster event.
        event_type            : Event type code.
        country               : Affected country.
        alert_level           : GDACS alert level.
        severity_text         : Severity description.
        lat                   : Latitude.
        lon                   : Longitude.
        report_url            : GDACS report URL.
        current_temp          : Current temperature (C).
        current_wind          : Current wind speed (km/h).
        current_condition     : Current weather condition.
        population_summary    : Who is at risk.
        infrastructure_summary: What infrastructure is threatened.
        danger_summary        : Immediate dangers.
        actions_residents     : Recommended actions (semicolon-separated).
        overall_severity      : low/moderate/high/critical.
        reasoning             : LLM reasoning text.
        confidence            : low/medium/high.

    Returns:
        Plain text briefing string.
    """
    try:
        # Reconstruct full dicts from flat args
        alert = {
            "event_id"     : None,
            "event_type"   : event_type,
            "name"         : event_name,
            "country"      : country,
            "affected"     : [country],
            "alert_level"  : alert_level,
            "severity_text": severity_text,
            "lat"          : lat,
            "lon"          : lon,
            "report_url"   : report_url
        }

        weather = {
            "data_available": True,
            "current": {
                "temp_c"   : current_temp,
                "wind_kmh" : current_wind,
                "condition": current_condition
            },
            "forecast"    : [],
            "danger_flags": []
        }

        impact = {
            "overall_severity"  : overall_severity,
            "confidence"        : confidence,
            "reasoning"         : reasoning,
            "llm_available"     : True,
            "population_at_risk": {
                "summary"              : population_summary,
                "vulnerability_factors": [],
                "estimated_scale"      : "regional"
            },
            "infrastructure_threats": {
                "summary"       : infrastructure_summary,
                "specific_risks": []
            },
            "immediate_dangers": {
                "summary"         : danger_summary,
                "danger_list"     : [],
                "time_sensitivity": "immediate"
            },
            "recommended_actions": {
                "for_residents" : actions_residents.split(";"),
                "for_responders": ["Coordinate with local authorities"]
            }
        }

        synth    = SynthesisOutputAgent()
        briefing = synth.synthesize(alert, weather, impact)

        reviewer = RiskReviewerAgent()
        reviewed = reviewer.review(briefing)

        return reviewed["text"]

    except Exception as e:
        return f"Error assembling briefing: {str(e)}"


# ══════════════════════════════════════════════════════════
# ADK AGENT DEFINITIONS
# ══════════════════════════════════════════════════════════

trigger_agent = LlmAgent(
    name        = "TriggerIngestionAgent",
    model       = GEMINI_MODEL,
    description = "Fetches the latest global disaster alert from GDACS.",
    instruction = """
You are the Trigger Ingestion Agent in a global disaster relief pipeline.

Your ONLY job: call fetch_disaster_alerts and report what you find.

1. Call fetch_disaster_alerts(min_severity="Green")
2. Parse the JSON result
3. Report the key fields: event name, country, alert level, severity, lat, lon

Be concise. Output the key fields clearly so the next agent can use them.
""",
    tools      = [fetch_disaster_alerts],
    output_key = "alert_data"
)

weather_agent = LlmAgent(
    name        = "WeatherContextAgent",
    model       = GEMINI_MODEL,
    description = "Fetches weather conditions for a disaster location.",
    instruction = """
You are the Weather Context Agent in a global disaster relief pipeline.

The previous agent found a disaster alert. Extract the latitude, longitude,
and country from the alert data in context, then fetch weather for that location.

1. Extract lat, lon, country from the alert data
2. Call fetch_weather_for_location(lat=<lat>, lon=<lon>, country=<country>)
3. Report key weather fields: temperature, wind speed, condition, 3-day forecast,
   and any danger flags

Be concise. Report the key fields clearly for the next agent.
""",
    tools      = [fetch_weather_for_location],
    output_key = "weather_data"
)

impact_agent = LlmAgent(
    name        = "HumanitarianImpactAgent",
    model       = IMPACT_MODEL,
    description = "Assesses humanitarian impact using LLM reasoning.",
    instruction = """
You are the Humanitarian Impact Agent in a global disaster relief pipeline.

Using the alert and weather data from previous agents, call assess_impact
with the relevant fields to get a humanitarian impact assessment.

Extract from the context:
- event_name, event_type, country, alert_level, severity_text, lat, lon
  (from alert data)
- current_temp, current_wind, current_condition
  (from weather data)
- forecast summaries for day 1, 2, 3
- danger_flags (comma-separated string, or empty string if none)

Then call assess_impact with all these fields.
Report the key impact fields: overall_severity, confidence, population summary,
infrastructure summary, danger summary, recommended actions, reasoning.
""",
    tools      = [assess_impact],
    output_key = "impact_data"
)

synthesis_agent = LlmAgent(
    name        = "SynthesisOutputAgent",
    model       = GEMINI_MODEL,
    description = "Assembles a plain-language disaster briefing.",
    instruction = """
You are the Synthesis and Review Agent — the final step in a disaster relief pipeline.

Using all the data from previous agents (alert, weather, impact), call build_briefing
to assemble and review a complete plain-language disaster briefing.

Extract from context:
From alert data: event_name, event_type, country, alert_level, severity_text,
                 lat, lon, report_url
From weather data: current_temp, current_wind, current_condition
From impact data: population_summary, infrastructure_summary, danger_summary,
                  actions_residents (join with semicolons),
                  overall_severity, reasoning, confidence

Call build_briefing with all these fields.
Output the final briefing text exactly as returned by the tool.
""",
    tools      = [build_briefing],
    output_key = "final_briefing"
)


# ══════════════════════════════════════════════════════════
# SEQUENTIAL ORCHESTRATOR — root_agent
# ADK looks for root_agent when running `adk run` or `adk web`
# ══════════════════════════════════════════════════════════
root_agent = SequentialAgent(
    name        = "DisasterReliefOrchestrator",
    description = (
        "Global disaster alert agent. Monitors GDACS for real-time "
        "disasters worldwide, enriches alerts with weather context and "
        "LLM humanitarian impact assessment, and produces plain-language "
        "briefings for affected populations."
    ),
    sub_agents  = [
        trigger_agent,
        weather_agent,
        impact_agent,
        synthesis_agent,
    ]
)


# ══════════════════════════════════════════════════════════
# DIRECT PYTHON RUN — python agents/orchestrator.py
# ══════════════════════════════════════════════════════════
async def run_pipeline(
    query: str = "Fetch the latest disaster alert and produce a briefing."
):
    """Run the full pipeline programmatically."""
    APP_NAME   = "disaster-relief-agent"
    USER_ID    = "user_001"
    SESSION_ID = "session_001"

    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name   = APP_NAME,
        user_id    = USER_ID,
        session_id = SESSION_ID
    )

    runner = Runner(
        agent           = root_agent,
        app_name        = APP_NAME,
        session_service = session_service
    )

    print(f"\n{'='*60}")
    print("  DISASTER RELIEF AGENT — ADK Pipeline v2")
    print(f"{'='*60}\n")

    content = types.Content(
        role  = "user",
        parts = [types.Part(text=query)]
    )

    final_output = None

    async for event in runner.run_async(
        user_id     = USER_ID,
        session_id  = SESSION_ID,
        new_message = content
    ):
        # Print intermediate agent outputs as they arrive
        if hasattr(event, "content") and event.content:
            for part in event.content.parts:
                if hasattr(part, "text") and part.text:
                    # Only print substantive outputs
                    text = part.text.strip()
                    if len(text) > 20 and not text.startswith("{"):
                        print(f"\n[Agent Output]\n{text}\n")

        if event.is_final_response():
            if event.content and event.content.parts:
                final_output = event.content.parts[0].text

    print(f"\n{'='*60}")
    print("  FINAL BRIEFING")
    print(f"{'='*60}")
    if final_output:
        print(final_output)
    else:
        print("No final output produced.")


if __name__ == "__main__":
    asyncio.run(run_pipeline())