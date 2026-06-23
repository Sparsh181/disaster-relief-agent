"""
Phase 0 — Save Historical Reference Events
Finds recent significant (Orange/Red) GDACS events and saves them
as cached JSON files in data/raw/ for use as demo/test data.
Run once: python save_reference_events.py
"""

import requests
import json
import os
from datetime import datetime
from gdacs.api import GDACSAPIReader

client = GDACSAPIReader()

# -------------------------------------------------------
# Known historical Orange/Red event IDs
# These were manually verified from gdacs.org event archive
# covering earthquake, flood, and tropical cyclone types
# -------------------------------------------------------
REFERENCE_EVENTS = [
    {
        "label": "Tropical Cyclone Chido - Mozambique (Dec 2024, Red)",
        "eventtype": "TC",
        "eventid": 1000985,
        "episodeid": None   # will use first episode
    },
    {
        "label": "Earthquake Vanuatu (Dec 2024, Red)",
        "eventtype": "EQ",
        "eventid": 1401310,
        "episodeid": None
    },
    {
        "label": "Flood Spain Valencia (Oct 2024, Red)",
        "eventtype": "FL",
        "eventid": 1102983,
        "episodeid": None
    }
]

# -------------------------------------------------------
# Also pull current live alerts for comparison
# -------------------------------------------------------
def fetch_live_alerts(limit=20):
    """Pull current live GDACS alerts and return as list of dicts"""
    print("\n=== FETCHING CURRENT LIVE ALERTS ===")
    events = client.latest_events()
    results = []

    for event in list(events.features)[:limit]:
        p = event['properties']
        coords = event['geometry']['coordinates']
        entry = {
            "name":        p.get('name'),
            "eventtype":   p.get('eventtype'),
            "eventid":     p.get('eventid'),
            "episodeid":   p.get('episodeid'),
            "alertlevel":  p.get('alertlevel'),
            "alertscore":  p.get('alertscore'),
            "country":     p.get('country'),
            "iso3":        p.get('iso3'),
            "fromdate":    p.get('fromdate'),
            "todate":      p.get('todate'),
            "severity":    p.get('severitydata', {}),
            "lat":         coords[1],
            "lon":         coords[0],
            "report_url":  p.get('url', {}).get('report'),
            "details_url": p.get('url', {}).get('details'),
            "fetched_at":  datetime.utcnow().isoformat()
        }
        results.append(entry)
        print(f"  [{p.get('alertlevel'):6}] {p.get('name')} | {p.get('country')}")

    return results


# -------------------------------------------------------
# Fetch a specific historical event by ID
# -------------------------------------------------------
def fetch_event_by_id(eventtype, eventid, episodeid=None):
    """Fetch a specific event from GDACS API by event ID"""
    url = "https://www.gdacs.org/gdacsapi/api/events/geteventdata"
    params = {"eventtype": eventtype, "eventid": eventid}
    if episodeid:
        params["episodeid"] = episodeid

    response = requests.get(url, params=params)
    if response.status_code != 200:
        print(f"  Failed: status {response.status_code}")
        return None

    data = response.json()
    props = data.get("properties", {})

    if not props:
        print(f"  No properties found in response")
        return None

    # Also fetch Open-Meteo weather for this event's location
    coords = data.get("geometry", {}).get("coordinates", [None, None])
    lon, lat = coords[0], coords[1]
    weather = None
    if lat and lon:
        weather = fetch_weather(lat, lon)

    return {
        "event":   props,
        "coords":  {"lat": lat, "lon": lon},
        "weather": weather,
        "fetched_at": datetime.utcnow().isoformat()
    }


# -------------------------------------------------------
# Fetch weather for a location
# -------------------------------------------------------
def fetch_weather(lat, lon):
    """Fetch current + 3-day forecast from Open-Meteo"""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude":        lat,
        "longitude":       lon,
        "current_weather": True,
        "daily":           "temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max",
        "timezone":        "auto",
        "forecast_days":   3
    }
    response = requests.get(url, params=params)
    if response.status_code != 200:
        return None
    return response.json()


# -------------------------------------------------------
# Main: fetch + save everything
# -------------------------------------------------------
def main():
    os.makedirs("data/raw", exist_ok=True)

    # 1. Save current live alerts
    live = fetch_live_alerts(limit=20)
    live_path = "data/raw/live_alerts.json"
    with open(live_path, "w") as f:
        json.dump(live, f, indent=2)
    print(f"\n✅ Saved {len(live)} live alerts → {live_path}")

    # 2. Save historical reference events
    print("\n=== FETCHING HISTORICAL REFERENCE EVENTS ===")
    saved = []

    for ref in REFERENCE_EVENTS:
        print(f"\nFetching: {ref['label']}")
        result = fetch_event_by_id(
            ref['eventtype'],
            ref['eventid'],
            ref.get('episodeid')
        )

        if result:
            props = result['event']
            print(f"  Name         : {props.get('name')}")
            print(f"  Country      : {props.get('country')}")
            print(f"  Alert Level  : {props.get('alertlevel')}")
            print(f"  Severity     : {props.get('severitydata', {}).get('severitytext')}")
            print(f"  Date         : {props.get('fromdate')}")
            print(f"  Weather OK   : {'Yes' if result['weather'] else 'No'}")

            # Save individual event file
            filename = f"data/raw/ref_{ref['eventtype']}_{ref['eventid']}.json"
            with open(filename, "w") as f:
                json.dump(result, f, indent=2)
            print(f"  ✅ Saved → {filename}")
            saved.append(filename)
        else:
            print(f"  ⚠️  No data returned — event ID may be wrong, trying search fallback...")

            # Fallback: search by event type in recent history
            fallback = client.latest_events(event_type=ref['eventtype'])
            print(f"  Found {len(fallback.features)} recent {ref['eventtype']} events as fallback")

    # 3. Summary
    print(f"\n{'='*50}")
    print(f"PHASE 0 DATA COLLECTION COMPLETE")
    print(f"{'='*50}")
    print(f"Live alerts saved  : data/raw/live_alerts.json ({len(live)} events)")
    print(f"Reference events   : {len(saved)} saved")
    for s in saved:
        print(f"  - {s}")
    print(f"\nNext step: commit to git, then start Phase 1 (Core Agents) on Jun 23")


if __name__ == "__main__":
    main()