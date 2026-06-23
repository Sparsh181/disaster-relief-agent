import requests
import json

def fetch_and_save_volcano():
    """
    Try two confirmed Orange GDACS volcano events:
    1. Fuego volcano, Guatemala — Mar 2025 (Orange) — event ID 1000109
    2. Fuego is on GDACS at: eventtype=VO, eventid=1000109
    """

    candidates = [
        {"label": "Fuego Volcano Guatemala (Mar 2025, Orange)", "eventtype": "VO", "eventid": 1000109},
        {"label": "Kanlaon Volcano Philippines (Mar 2026)",      "eventtype": "VO", "eventid": 1000118},
        {"label": "Ibu Volcano Indonesia (May 2026)",            "eventtype": "VO", "eventid": 1000120},
    ]

    for candidate in candidates:
        print(f"\nTrying: {candidate['label']}")
        url = "https://www.gdacs.org/gdacsapi/api/events/geteventdata"
        params = {
            "eventtype": candidate["eventtype"],
            "eventid":   candidate["eventid"]
        }

        response = requests.get(url, params=params)
        print(f"Status: {response.status_code}")

        data = response.json()
        props = data.get("properties", {})

        if not props:
            print("  No data — trying next...")
            continue

        print(f"  Name        : {props.get('name')}")
        print(f"  Country     : {props.get('country')}")
        print(f"  Alert Level : {props.get('alertlevel')}")
        print(f"  Severity    : {props.get('severitydata', {}).get('severitytext')}")
        print(f"  Date        : {props.get('fromdate')}")

        # Also get weather for this location
        coords = data.get("geometry", {}).get("coordinates", [None, None])
        lon, lat = coords[0], coords[1]
        weather = None
        if lat and lon:
            weather_url = "https://api.open-meteo.com/v1/forecast"
            weather_params = {
                "latitude": lat, "longitude": lon,
                "current_weather": True,
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max",
                "timezone": "auto", "forecast_days": 3
            }
            w = requests.get(weather_url, params=weather_params)
            weather = w.json() if w.status_code == 200 else None
            print(f"  Weather OK  : {'Yes' if weather else 'No'}")

        # Save it
        result = {
            "event":      props,
            "coords":     {"lat": lat, "lon": lon},
            "weather":    weather,
            "fetched_at": __import__("datetime").datetime.utcnow().isoformat()
        }

        filename = f"data/raw/ref_VO_{candidate['eventid']}.json"
        with open(filename, "w") as f:
            json.dump(result, f, indent=2)
        print(f"  ✅ Saved → {filename}")
        break  # stop after first successful one

fetch_and_save_volcano()