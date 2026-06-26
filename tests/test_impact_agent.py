import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.trigger_ingestion_agent import TriggerIngestionAgent
from agents.weather_context_agent   import WeatherContextAgent
from agents.humanitarian_impact_agent import HumanitarianImpactAgent

trigger = TriggerIngestionAgent(min_alert_level="Green", max_results=5)
weather = WeatherContextAgent()
impact  = HumanitarianImpactAgent()

# ── Test 1: Live alert pipeline ────────────────────────────
print("=== TEST 1: LIVE ALERT PIPELINE ===\n")
results = impact.assess_from_pipeline(trigger, weather, max_alerts=2)

for r in results:
    print(f"\n{'='*55}")
    print(f"Event  : {r['alert']['name']}")
    print(f"Level  : {r['alert']['alert_level']}")
    print(f"Weather: {r['weather']['current'].get('temp_c')}°C, "
          f"{r['weather']['current'].get('condition')}")
    print(f"\nIMPACT ASSESSMENT:")
    print(json.dumps(r['impact'], indent=2))


# ── Test 2: Reference events from data/raw/ ────────────────
print("\n\n=== TEST 2: REFERENCE EVENTS (saved historical data) ===\n")

ref_files = [
    "data/raw/ref_TC_1000985.json",
    "data/raw/ref_FL_1102983.json",
    "data/raw/ref_VO_1000109.json"
]

for path in ref_files:
    if not os.path.exists(path):
        print(f"Skipping {path} — file not found")
        continue

    with open(path) as f:
        ref = json.load(f)

    # Convert reference event format to alert dict format
    props = ref.get("event", {})
    coords = ref.get("coords", {})

    alert = {
        "event_id"      : props.get("eventid"),
        "event_type"    : props.get("eventtype"),
        "name"          : props.get("name"),
        "country"       : props.get("country"),
        "affected"      : [c["countryname"] for c in props.get("affectedcountries", [])],
        "alert_level"   : props.get("alertlevel"),
        "severity_text" : props.get("severitydata", {}).get("severitytext"),
        "from_date"     : props.get("fromdate"),
        "lat"           : coords.get("lat"),
        "lon"           : coords.get("lon")
    }

    # Use saved weather or fetch fresh
    saved_weather = ref.get("weather")
    if not saved_weather:
        saved_weather = weather.fetch(alert["lat"], alert["lon"],
                                      alert["country"])

    print(f"\n{'='*55}")
    print(f"Reference Event : {alert['name']}")
    print(f"Alert Level     : {alert['alert_level']}")

    result = impact.assess(alert, saved_weather)
    print(json.dumps(result, indent=2))