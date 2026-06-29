"""
FastAPI REST API — Disaster Relief Agent
-----------------------------------------
Exposes the agent system via HTTP endpoints.
Used by the Chrome extension, dashboard, and CLI.

Endpoints:
  GET  /alerts              → recent alerts from DB
  GET  /alerts/nearby       → alerts filtered by user location
  GET  /briefing/{event_id} → full briefing for an event
  POST /users/register      → register for notifications
  GET  /stats               → system stats
  GET  /health              → health check

Usage:
  uvicorn api.main:app --reload --port 8000
"""

import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime, timezone

from system.database  import Database
from system.notifier  import haversine_distance
from mcp_server.tools import get_disaster_alerts, get_weather, get_full_briefing

# ── App setup ───────────────────────────────────────────────
app = FastAPI(
    title       = "Disaster Relief Agent API",
    description = "Real-time global disaster alerts + humanitarian briefings",
    version     = "1.0.0"
)

# CORS — allow Chrome extension to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["*"],  # tighten in production
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

db = Database()
db.init()


# ── Request/Response models ─────────────────────────────────
class UserRegistration(BaseModel):
    name      : str
    email     : str
    lat       : float
    lon       : float
    radius_km : float = 500.0
    min_alert : str   = "Orange"


# ══════════════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════════════

@app.get("/health")
def health():
    """Health check endpoint."""
    return {
        "status"    : "ok",
        "timestamp" : datetime.now(timezone.utc).isoformat(),
        "service"   : "disaster-relief-agent"
    }


@app.get("/stats")
def get_stats():
    """System stats — alert counts, briefing counts, users."""
    return db.get_stats()


@app.get("/alerts")
def get_alerts(limit: int = Query(20, ge=1, le=100)):
    """
    Get recent disaster alerts from the database.
    Returns alerts seen by the scheduler, most recent first.
    """
    alerts = db.get_recent_alerts(limit=limit)
    return {"alerts": alerts, "count": len(alerts)}


@app.get("/alerts/live")
def get_live_alerts(
    min_severity: str = Query("Green"),
    event_type  : str = Query("ALL"),
    max_results : int = Query(10, ge=1, le=20)
):
    """
    Fetch live alerts directly from GDACS (not from DB).
    Use this for the Chrome extension's real-time feed.
    """
    result = get_disaster_alerts(min_severity, event_type, max_results)
    return json.loads(result)


@app.get("/alerts/nearby")
def get_nearby_alerts(
    lat      : float = Query(..., description="User latitude"),
    lon      : float = Query(..., description="User longitude"),
    radius_km: float = Query(500, description="Search radius in km"),
    min_severity: str = Query("Green")
):
    """
    Get live alerts within a given radius of a location.
    Used by the Chrome extension to show alerts near the user.
    """
    # Input validation
    if not (-90 <= lat <= 90):
        raise HTTPException(400, "Invalid latitude")
    if not (-180 <= lon <= 180):
        raise HTTPException(400, "Invalid longitude")
    if radius_km <= 0 or radius_km > 20000:
        raise HTTPException(400, "Invalid radius_km")

    # Fetch live alerts
    result = get_disaster_alerts(min_severity, "ALL", 20)
    data   = json.loads(result)
    alerts = data.get("alerts", [])

    # Filter by distance
    nearby = []
    for alert in alerts:
        dist = haversine_distance(
            lat, lon,
            alert.get("lat", 0),
            alert.get("lon", 0)
        )
        if dist <= radius_km:
            alert["distance_km"] = round(dist, 1)
            nearby.append(alert)

    # Sort by distance
    nearby.sort(key=lambda x: x["distance_km"])

    return {
        "alerts"        : nearby,
        "count"         : len(nearby),
        "user_location" : {"lat": lat, "lon": lon},
        "radius_km"     : radius_km,
        "fetched_at"    : datetime.now(timezone.utc).isoformat()
    }


@app.get("/briefing/{event_type}/{event_id}")
def get_briefing(event_type: str, event_id: int,
                 include_impact: bool = Query(False)):
    """
    Get full briefing for a specific GDACS event.
    include_impact=True triggers LLM assessment (uses quota).
    """
    valid_types = ["EQ", "TC", "FL", "VO", "WF", "DR"]
    if event_type.upper() not in valid_types:
        raise HTTPException(400, f"Invalid event_type. Must be: {valid_types}")

    # Check DB first
    cached = db.get_briefing(str(event_id))
    if cached:
        return {
            "briefing_text": cached.get("briefing_text"),
            "event_id"     : event_id,
            "source"       : "cache",
            "generated_at" : cached.get("generated_at")
        }

    # Run pipeline
    result = get_full_briefing(event_id, event_type.upper(), include_impact)
    data   = json.loads(result)

    if "error" in data:
        raise HTTPException(404, data["error"])

    return {**data, "source": "live"}


@app.post("/users/register")
def register_user(user: UserRegistration):
    """
    Register a user for location-aware notifications.
    Users only receive alerts within their radius + severity threshold.
    """
    if not (-90 <= user.lat <= 90):
        raise HTTPException(400, "Invalid latitude")
    if not (-180 <= user.lon <= 180):
        raise HTTPException(400, "Invalid longitude")
    if user.min_alert not in ["Green", "Orange", "Red"]:
        raise HTTPException(400, "min_alert must be Green, Orange, or Red")

    user_id = db.register_user(
        name      = user.name,
        email     = user.email,
        lat       = user.lat,
        lon       = user.lon,
        radius_km = user.radius_km,
        min_alert = user.min_alert
    )

    return {
        "message" : "User registered successfully",
        "user_id" : user_id,
        "email"   : user.email,
        "radius_km": user.radius_km,
        "min_alert": user.min_alert
    }


@app.get("/briefings/recent")
def get_recent_briefings(limit: int = Query(10, ge=1, le=50)):
    """Get most recent briefings from the database."""
    briefings = db.get_recent_briefings(limit=limit)
    return {"briefings": briefings, "count": len(briefings)}
