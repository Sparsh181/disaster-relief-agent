import requests

def get_weather(lat, lon, location_name=""):
    """
    Fetch current weather + 3-day forecast for a given lat/long
    using Open-Meteo (free, no API key needed)
    """
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current_weather": True,
        "hourly": "temperature_2m,precipitation_probability,windspeed_10m",
        "daily": "weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max",
        "timezone": "auto",
        "forecast_days": 3
    }

    response = requests.get(url, params=params)
    data = response.json()

    print(f"\n=== WEATHER FOR {location_name.upper()} ({lat}, {lon}) ===")

    # Current conditions
    current = data.get("current_weather", {})
    print(f"""
    Current Conditions:
    Temperature  : {current.get('temperature')}°C
    Wind Speed   : {current.get('windspeed')} km/h
    Wind Dir     : {current.get('winddirection')}°
    Weather Code : {current.get('weathercode')}
    Is Day       : {'Yes' if current.get('is_day') else 'No'}
    """)

    # 3-day forecast
    daily = data.get("daily", {})
    dates = daily.get("time", [])
    max_temps = daily.get("temperature_2m_max", [])
    min_temps = daily.get("temperature_2m_min", [])
    precip = daily.get("precipitation_sum", [])
    wind_max = daily.get("windspeed_10m_max", [])

    print("    3-Day Forecast:")
    for i in range(len(dates)):
        print(f"""
        Date         : {dates[i]}
        Temp Max/Min : {max_temps[i]}°C / {min_temps[i]}°C
        Precipitation: {precip[i]} mm
        Max Wind     : {wind_max[i]} km/h
        """)

    return data


# --- Test with real coords from our GDACS events ---

# Guatemala earthquake location
get_weather(13.4249, -90.7542, "Guatemala (Earthquake)")

# South Korea flood location
get_weather(37.5665, 126.9780, "South Korea (Flood)")

# Japan typhoon location
get_weather(17.5, 127.8, "Japan (Typhoon MEKKHALA-26)")