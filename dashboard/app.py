"""
Streamlit Dashboard — Disaster Relief Agent
---------------------------------------------
Visual dashboard showing live alerts, system stats,
recent briefings, and rate limiter / eval metrics.

Reads from the FastAPI backend (must be running):
  uvicorn api.main:app --port 8000

Usage:
  streamlit run dashboard/app.py
"""

import sys
import os
import json
import requests
import streamlit as st
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

API = "http://localhost:8000"

st.set_page_config(
    page_title="Disaster Relief Agent",
    page_icon="🌍",
    layout="wide"
)

# ── Helper: safe API call ───────────────────────────────────
def api_get(path, params=None):
    try:
        r = requests.get(f"{API}{path}", params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"⚠️ Cannot reach API at {API}{path} — {e}")
        st.info("Make sure the API is running: `uvicorn api.main:app --port 8000`")
        return None


# ── Header ───────────────────────────────────────────────────
st.title("🌍 Disaster Relief Agent — Live Dashboard")
st.caption("Global disaster alerts, weather context, and AI humanitarian briefings — powered by GDACS + Open-Meteo + Gemini")

health = api_get("/health")
if health:
    st.success(f"✅ System online — {health['timestamp']}")
else:
    st.stop()

st.divider()

# ── Stats row ────────────────────────────────────────────────
stats = api_get("/stats")
if stats:
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("Total Alerts", stats["total_alerts"])
    col2.metric("Briefings Generated", stats["total_briefings"])
    col3.metric("Registered Users", stats["total_users"])
    col4.metric("Notifications Sent", stats["notifications_sent"])
    col5.metric("🔴 Red Alerts", stats["red_alerts"])
    col6.metric("🟠 Orange Alerts", stats["orange_alerts"])

st.divider()

# ── Sidebar controls ─────────────────────────────────────────
st.sidebar.header("⚙️ Filters")
min_severity = st.sidebar.selectbox("Minimum Severity", ["Green", "Orange", "Red"], index=0)
event_type   = st.sidebar.selectbox(
    "Event Type",
    ["ALL", "EQ", "TC", "FL", "VO", "WF", "DR"],
    format_func=lambda x: {
        "ALL": "All Types", "EQ": "🌍 Earthquake", "TC": "🌀 Cyclone",
        "FL": "🌊 Flood", "VO": "🌋 Volcano", "WF": "🔥 Wildfire", "DR": "☀️ Drought"
    }.get(x, x)
)
max_results = st.sidebar.slider("Max Results", 5, 20, 10)

st.sidebar.divider()
st.sidebar.header("📍 Check Nearby Alerts")
user_lat = st.sidebar.number_input("Your Latitude", value=17.385, format="%.4f")
user_lon = st.sidebar.number_input("Your Longitude", value=78.486, format="%.4f")
radius   = st.sidebar.slider("Radius (km)", 100, 20000, 2000)

st.sidebar.divider()
if st.sidebar.button("🔄 Refresh Data"):
    st.rerun()

# ── Main layout ──────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "🔴 Live Alerts", "📍 Nearby Alerts", "📋 Recent Briefings", "📊 System Health"
])

# ── TAB 1: Live Alerts ──────────────────────────────────────
with tab1:
    st.subheader("Live Global Disaster Alerts (from GDACS)")

    data = api_get("/alerts/live", params={
        "min_severity": min_severity,
        "event_type"  : event_type,
        "max_results" : max_results
    })

    if data and data.get("alerts"):
        for alert in data["alerts"]:
            level = alert.get("alert_level", "Green")
            color = {"Red": "🔴", "Orange": "🟠", "Green": "🟢"}.get(level, "⚪")

            with st.expander(f"{color} **{alert['name']}** — {alert.get('country','')}"):
                c1, c2, c3 = st.columns(3)
                c1.write(f"**Type:** {alert.get('event_type')}")
                c1.write(f"**Severity:** {alert.get('severity_text')}")
                c2.write(f"**Alert Level:** {level}")
                c2.write(f"**Date:** {alert.get('from_date','')[:16]}")
                c3.write(f"**Location:** {alert.get('lat'):.2f}, {alert.get('lon'):.2f}")
                if alert.get("report_url"):
                    c3.markdown(f"[📄 GDACS Report]({alert['report_url']})")

                if st.button(f"Get Full Briefing", key=f"brief_{alert['event_id']}"):
                    with st.spinner("Generating briefing..."):
                        briefing = api_get(
                            f"/briefing/{alert['event_type']}/{alert['event_id']}",
                            params={"include_impact": False}
                        )
                        if briefing:
                            st.text(briefing.get("briefing_text", "No briefing text available"))
    else:
        st.info("No alerts match the current filters.")

# ── TAB 2: Nearby Alerts ─────────────────────────────────────
with tab2:
    st.subheader(f"Alerts within {radius} km of ({user_lat}, {user_lon})")

    nearby = api_get("/alerts/nearby", params={
        "lat": user_lat, "lon": user_lon,
        "radius_km": radius, "min_severity": min_severity
    })

    if nearby and nearby.get("alerts"):
        # Map view
        map_data = [
            {"lat": a["lat"], "lon": a["lon"]}
            for a in nearby["alerts"] if a.get("lat") and a.get("lon")
        ]
        if map_data:
            st.map(map_data, zoom=2)

        st.write(f"**{nearby['count']} alerts found**")
        for alert in nearby["alerts"]:
            level = alert.get("alert_level", "Green")
            color = {"Red": "🔴", "Orange": "🟠", "Green": "🟢"}.get(level, "⚪")
            st.write(f"{color} **{alert['name']}** — {alert.get('distance_km')} km away "
                     f"— {alert.get('severity_text')}")
    else:
        st.info("No alerts within this radius.")

# ── TAB 3: Recent Briefings ──────────────────────────────────
with tab3:
    st.subheader("Recently Generated Briefings")

    briefings = api_get("/briefings/recent", params={"limit": 10})

    if briefings and briefings.get("briefings"):
        for b in briefings["briefings"]:
            level = b.get("alert_level", "Green")
            color = {"Red": "🔴", "Orange": "🟠", "Green": "🟢"}.get(level, "⚪")
            passed = "✅" if b.get("review_passed") else "⛔"

            with st.expander(f"{color} {b.get('name')} — {passed} Reviewed — {b.get('generated_at','')[:16]}"):
                st.text(b.get("briefing_text", "")[:800])
                st.caption(f"LLM used: {bool(b.get('llm_used'))} | "
                          f"Review flags: {b.get('review_flags', 0)}")
    else:
        st.info("No briefings generated yet. Run the scheduler to generate some.")

# ── TAB 4: System Health ─────────────────────────────────────
with tab4:
    st.subheader("System Health & Metrics")

    # Eval results if available
    eval_path = "data/processed/eval_results.json"
    if os.path.exists(eval_path):
        with open(eval_path) as f:
            eval_data = json.load(f)

        st.write("**Latest Evaluation Run**")
        c1, c2, c3 = st.columns(3)
        c1.metric("Coverage Rate", eval_data.get("coverage_rate", "N/A"))
        c2.metric("Avg Latency", f"{eval_data.get('avg_latency_s', 0)}s")
        c3.metric("Tool Success Rate", eval_data.get("tool_call_success_rate", "N/A"))
        st.caption(f"Run at: {eval_data.get('run_at', 'N/A')}")
    else:
        st.info("No eval results found. Run: `python eval/metrics.py --save`")

    st.divider()
    st.write("**Architecture**")
    st.code("""
GDACS (trigger) → Weather Context (Open-Meteo) → Humanitarian Impact (Gemini LLM)
       → Synthesis (plain-language briefing) → Risk Reviewer (safety check)
       → SQLite DB → FastAPI → Chrome Extension / Dashboard / Email Notifications
    """, language="text")

st.divider()
st.caption("🌍 Disaster Relief Agent | Agents for Good Track | GDACS + Open-Meteo + Gemini + Google ADK")