"""
Weather Context Agent
----------------------
Takes a lat/long from the Trigger Agent's alert output
and fetches current weather conditions + 3-day forecast
from Open-Meteo (free, no API key, global coverage).

Input  : lat (float), lon (float)
Output : clean structured dict with current + forecast data
"""

import requests
from datetime import datetime

# Open-Meteo weather code → human readable description
WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Icy fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Heavy drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    77: "Snow grains",
    80: "Slight showers", 81: "Moderate showers", 82: "Violent showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm w/ hail", 99: "Thunderstorm w/ heavy hail"
}


class WeatherContextAgent:
    """
    Fetches current + forecast weather for a given location
    using Open-Meteo API (no key required).
    """

    BASE_URL = "https://api.open-meteo.com/v1/forecast"

    def fetch(self, lat, lon, location_name=""):
        """
        Main method — fetches weather for a lat/long.

        Args:
            lat           : latitude (float)
            lon           : longitude (float)
            location_name : optional label for logging

        Returns:
            dict with current conditions + 3-day forecast,
            or None if the API call fails
        """
        label = location_name or f"({lat}, {lon})"
        print(f"[WeatherAgent] Fetching weather for {label}...")

        params = {
            "latitude"        : lat,
            "longitude"       : lon,
            "current_weather" : True,
            "hourly"          : "precipitation_probability",
            "daily"           : (
                "temperature_2m_max,"
                "temperature_2m_min,"
                "precipitation_sum,"
                "windspeed_10m_max,"
                "weathercode"
            ),
            "timezone"        : "auto",
            "forecast_days"   : 3
        }

        try:
            response = requests.get(self.BASE_URL, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.Timeout:
            print(f"[WeatherAgent] ERROR: Request timed out for {label}")
            return self._empty_result(lat, lon, location_name)
        except requests.exceptions.RequestException as e:
            print(f"[WeatherAgent] ERROR: API call failed — {e}")
            return self._empty_result(lat, lon, location_name)

        return self._parse(data, lat, lon, location_name)

    def fetch_for_alert(self, alert):
        """
        Convenience method — accepts a Trigger Agent alert dict
        directly and pulls weather for its lat/long.

        Args:
            alert : dict from TriggerIngestionAgent.fetch()
        """
        return self.fetch(
            lat           = alert["lat"],
            lon           = alert["lon"],
            location_name = alert.get("country", "")
        )

    # ── private helpers ────────────────────────────────────

    def _parse(self, data, lat, lon, location_name):
        """
        Parses Open-Meteo response into a clean flat dict.
        """
        current = data.get("current_weather", {})
        daily   = data.get("daily", {})

        # Build 3-day forecast list
        forecast = []
        dates     = daily.get("time", [])
        max_temps = daily.get("temperature_2m_max", [])
        min_temps = daily.get("temperature_2m_min", [])
        precip    = daily.get("precipitation_sum", [])
        wind_max  = daily.get("windspeed_10m_max", [])
        wcodes    = daily.get("weathercode", [])

        for i in range(len(dates)):
            forecast.append({
                "date"         : dates[i],
                "temp_max_c"   : max_temps[i] if i < len(max_temps) else None,
                "temp_min_c"   : min_temps[i] if i < len(min_temps) else None,
                "precip_mm"    : precip[i]    if i < len(precip)    else None,
                "wind_max_kmh" : wind_max[i]  if i < len(wind_max)  else None,
                "condition"    : WEATHER_CODES.get(
                                   wcodes[i] if i < len(wcodes) else 0,
                                   "Unknown"
                                 )
            })

        # Danger flags — used by Humanitarian Impact Agent
        danger_flags = self._assess_danger(current, forecast)

        result = {
            # Location
            "lat"           : lat,
            "lon"           : lon,
            "location_name" : location_name,
            "timezone"      : data.get("timezone", "Unknown"),

            # Current conditions
            "current": {
                "temp_c"      : current.get("temperature"),
                "wind_kmh"    : current.get("windspeed"),
                "wind_dir"    : current.get("winddirection"),
                "condition"   : WEATHER_CODES.get(
                                  current.get("weathercode", 0), "Unknown"
                                ),
                "is_day"      : bool(current.get("is_day", 1))
            },

            # 3-day forecast
            "forecast"      : forecast,

            # Danger summary for LLM agent
            "danger_flags"  : danger_flags,

            # Metadata
            "fetched_at"    : datetime.utcnow().isoformat(),
            "data_available": True
        }

        print(f"[WeatherAgent] ✅ Weather fetched — "
              f"{result['current']['temp_c']}°C, "
              f"{result['current']['wind_kmh']} km/h winds, "
              f"{result['current']['condition']}")

        return result

    def _assess_danger(self, current, forecast):
        """
        Simple rule-based danger flags passed to the
        Humanitarian Impact Agent to aid LLM reasoning.
        """
        flags = []

        wind = current.get("windspeed", 0)
        if wind >= 120:  flags.append("EXTREME_WINDS")
        elif wind >= 60: flags.append("HIGH_WINDS")
        elif wind >= 30: flags.append("MODERATE_WINDS")

        if forecast:
            total_precip = sum(
                d["precip_mm"] for d in forecast
                if d["precip_mm"] is not None
            )
            max_wind = max(
                (d["wind_max_kmh"] for d in forecast
                 if d["wind_max_kmh"] is not None),
                default=0
            )
            if total_precip >= 150: flags.append("EXTREME_RAINFALL_3DAY")
            elif total_precip >= 50: flags.append("HEAVY_RAINFALL_3DAY")

            if max_wind >= 120: flags.append("EXTREME_WINDS_FORECAST")
            elif max_wind >= 60: flags.append("HIGH_WINDS_FORECAST")

        return flags

    def _empty_result(self, lat, lon, location_name):
        """
        Returns a safe empty result when the API call fails,
        so downstream agents can handle it gracefully.
        """
        print(f"[WeatherAgent] WARNING: Returning empty weather result")
        return {
            "lat"            : lat,
            "lon"            : lon,
            "location_name"  : location_name,
            "timezone"       : "Unknown",
            "current"        : {},
            "forecast"       : [],
            "danger_flags"   : [],
            "fetched_at"     : datetime.utcnow().isoformat(),
            "data_available" : False
        }