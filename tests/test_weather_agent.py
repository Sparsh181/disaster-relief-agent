import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.trigger_ingestion_agent import TriggerIngestionAgent
from agents.weather_context_agent import WeatherContextAgent

# ── smoke test: trigger → weather (agents talking to each other)
trigger = TriggerIngestionAgent(min_alert_level="Green", max_results=5)
weather = WeatherContextAgent()

print("=== TRIGGER → WEATHER PIPELINE TEST ===\n")
alerts = trigger.fetch()

for alert in alerts[:3]:
    print(f"\n{'='*50}")
    print(f"Alert  : {alert['name']}")
    print(f"Country: {alert['country']} | Level: {alert['alert_level']}")

    w = weather.fetch_for_alert(alert)

    if w["data_available"]:
        print(f"Temp   : {w['current']['temp_c']}°C")
        print(f"Wind   : {w['current']['wind_kmh']} km/h")
        print(f"Cond   : {w['current']['condition']}")
        print(f"Danger : {w['danger_flags'] or 'None'}")
        print(f"Forecast (3 days):")
        for day in w["forecast"]:
            print(f"  {day['date']} | "
                  f"Max {day['temp_max_c']}°C | "
                  f"Rain {day['precip_mm']}mm | "
                  f"Wind {day['wind_max_kmh']} km/h | "
                  f"{day['condition']}")
    else:
        print("Weather data unavailable for this location")