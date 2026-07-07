import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import requests

# Ensure the root directory is in python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.weather_context_agent import WeatherContextAgent, WEATHER_CODES

class TestWeatherContextAgent(unittest.TestCase):

    def setUp(self):
        self.agent = WeatherContextAgent()

    @patch('agents.weather_context_agent.requests.get')
    def test_fetch_success(self, mock_get):
        # Create a mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "latitude": -17.7,
            "longitude": 168.3,
            "timezone": "Pacific/Efate",
            "current_weather": {
                "temperature": 24.5,
                "windspeed": 35.0,
                "winddirection": 120,
                "weathercode": 61,  # Slight rain
                "is_day": 1
            },
            "daily": {
                "time": ["2026-07-07", "2026-07-08", "2026-07-09"],
                "temperature_2m_max": [26.0, 27.0, 25.0],
                "temperature_2m_min": [21.0, 22.0, 20.0],
                "precipitation_sum": [10.0, 60.0, 5.0],
                "windspeed_10m_max": [40.0, 65.0, 30.0],
                "weathercode": [61, 81, 3]
            }
        }
        mock_get.return_value = mock_response

        res = self.agent.fetch(lat=-17.7, lon=168.3, location_name="Vanuatu")

        # Verify requests.get call arguments
        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        self.assertEqual(args[0], self.agent.BASE_URL)
        self.assertEqual(kwargs["params"]["latitude"], -17.7)
        self.assertEqual(kwargs["params"]["longitude"], 168.3)
        self.assertEqual(kwargs["timeout"], 10)

        # Verify response parsing
        self.assertTrue(res["data_available"])
        self.assertEqual(res["lat"], -17.7)
        self.assertEqual(res["lon"], 168.3)
        self.assertEqual(res["location_name"], "Vanuatu")
        self.assertEqual(res["timezone"], "Pacific/Efate")
        self.assertEqual(res["current"]["temp_c"], 24.5)
        self.assertEqual(res["current"]["wind_kmh"], 35.0)
        self.assertEqual(res["current"]["condition"], "Slight rain")
        self.assertEqual(res["current"]["is_day"], True)

        # Forecast checks
        self.assertEqual(len(res["forecast"]), 3)
        self.assertEqual(res["forecast"][0]["date"], "2026-07-07")
        self.assertEqual(res["forecast"][0]["temp_max_c"], 26.0)
        self.assertEqual(res["forecast"][0]["precip_mm"], 10.0)
        self.assertEqual(res["forecast"][0]["condition"], "Slight rain")

        # Danger flags (35.0 km/h wind speed = MODERATE_WINDS; Max forecast wind speed 65.0 = HIGH_WINDS_FORECAST; sum precip 75.0 = HEAVY_RAINFALL_3DAY)
        self.assertIn("MODERATE_WINDS", res["danger_flags"])
        self.assertIn("HEAVY_RAINFALL_3DAY", res["danger_flags"])
        self.assertIn("HIGH_WINDS_FORECAST", res["danger_flags"])

    @patch('agents.weather_context_agent.requests.get')
    def test_fetch_timeout(self, mock_get):
        mock_get.side_effect = requests.exceptions.Timeout("Connection timed out")

        res = self.agent.fetch(lat=10.0, lon=20.0, location_name="TimeoutLand")

        self.assertFalse(res["data_available"])
        self.assertEqual(res["lat"], 10.0)
        self.assertEqual(res["lon"], 20.0)
        self.assertEqual(res["location_name"], "TimeoutLand")
        self.assertEqual(res["current"], {})
        self.assertEqual(res["forecast"], [])
        self.assertEqual(res["danger_flags"], [])

    @patch('agents.weather_context_agent.requests.get')
    def test_fetch_request_exception(self, mock_get):
        mock_get.side_effect = requests.exceptions.RequestException("API Error")

        res = self.agent.fetch(lat=10.0, lon=20.0, location_name="ErrorLand")

        self.assertFalse(res["data_available"])
        self.assertEqual(res["current"], {})
        self.assertEqual(res["forecast"], [])

    @patch('agents.weather_context_agent.WeatherContextAgent.fetch')
    def test_fetch_for_alert(self, mock_fetch):
        mock_alert = {
            "lat": 45.0,
            "lon": -90.0,
            "country": "USA",
            "name": "Storm alert"
        }
        self.agent.fetch_for_alert(mock_alert)
        mock_fetch.assert_called_once_with(lat=45.0, lon=-90.0, location_name="USA")

    def test_assess_danger_wind_thresholds(self):
        # Test extreme wind (current)
        flags = self.agent._assess_danger({"windspeed": 125}, [])
        self.assertIn("EXTREME_WINDS", flags)

        # Test high wind (current)
        flags = self.agent._assess_danger({"windspeed": 65}, [])
        self.assertIn("HIGH_WINDS", flags)

        # Test moderate wind (current)
        flags = self.agent._assess_danger({"windspeed": 35}, [])
        self.assertIn("MODERATE_WINDS", flags)

        # Test no wind flags when low wind speed
        flags = self.agent._assess_danger({"windspeed": 15}, [])
        self.assertNotIn("EXTREME_WINDS", flags)
        self.assertNotIn("HIGH_WINDS", flags)
        self.assertNotIn("MODERATE_WINDS", flags)

    def test_assess_danger_forecast_thresholds(self):
        # Test extreme rainfall (3-day forecast)
        forecast_heavy_rain = [
            {"precip_mm": 50.0, "wind_max_kmh": 10.0},
            {"precip_mm": 110.0, "wind_max_kmh": 10.0},
            {"precip_mm": 10.0, "wind_max_kmh": 10.0}
        ]
        flags = self.agent._assess_danger({"windspeed": 10}, forecast_heavy_rain)
        self.assertIn("EXTREME_RAINFALL_3DAY", flags)

        # Test heavy rainfall
        forecast_medium_rain = [
            {"precip_mm": 20.0, "wind_max_kmh": 10.0},
            {"precip_mm": 35.0, "wind_max_kmh": 10.0},
            {"precip_mm": 5.0, "wind_max_kmh": 10.0}
        ]
        flags = self.agent._assess_danger({"windspeed": 10}, forecast_medium_rain)
        self.assertIn("HEAVY_RAINFALL_3DAY", flags)
        self.assertNotIn("EXTREME_RAINFALL_3DAY", flags)

        # Test extreme wind forecast
        forecast_extreme_wind = [
            {"precip_mm": 0.0, "wind_max_kmh": 130.0},
            {"precip_mm": 0.0, "wind_max_kmh": 40.0}
        ]
        flags = self.agent._assess_danger({"windspeed": 10}, forecast_extreme_wind)
        self.assertIn("EXTREME_WINDS_FORECAST", flags)

        # Test high wind forecast
        forecast_high_wind = [
            {"precip_mm": 0.0, "wind_max_kmh": 70.0},
            {"precip_mm": 0.0, "wind_max_kmh": 40.0}
        ]
        flags = self.agent._assess_danger({"windspeed": 10}, forecast_high_wind)
        self.assertIn("HIGH_WINDS_FORECAST", flags)
        self.assertNotIn("EXTREME_WINDS_FORECAST", flags)

    def test_parse_mismatched_forecast_lists(self):
        # Verify that mismatched array lengths are handled gracefully
        data = {
            "timezone": "UTC",
            "current_weather": {},
            "daily": {
                "time": ["2026-07-07", "2026-07-08"],
                # Mismatch: temperature_2m_max only has 1 value
                "temperature_2m_max": [30.0],
                # precipitation_sum has 0 values
                "precipitation_sum": [],
                # weathercode is completely missing
            }
        }
        res = self.agent._parse(data, 1.0, 2.0, "Test")
        self.assertEqual(len(res["forecast"]), 2)
        # First day has temp_max_c
        self.assertEqual(res["forecast"][0]["temp_max_c"], 30.0)
        self.assertIsNone(res["forecast"][0]["precip_mm"])
        # Second day has None for temp_max_c since index 1 is out of bounds
        self.assertIsNone(res["forecast"][1]["temp_max_c"])
        # Both have None for precip_mm since precipitation_sum is empty
        self.assertIsNone(res["forecast"][1]["precip_mm"])
        # Condition defaults to "Clear sky" (code 0 fallback) if missing
        self.assertEqual(res["forecast"][0]["condition"], "Clear sky")

    def test_empty_result(self):
        res = self.agent._empty_result(1.0, 2.0, "Empty")
        self.assertFalse(res["data_available"])
        self.assertEqual(res["lat"], 1.0)
        self.assertEqual(res["lon"], 2.0)
        self.assertEqual(res["location_name"], "Empty")
        self.assertEqual(res["timezone"], "Unknown")
        self.assertEqual(res["current"], {})
        self.assertEqual(res["forecast"], [])
        self.assertEqual(res["danger_flags"], [])
        self.assertIsNotNone(res["fetched_at"])


if __name__ == '__main__':
    unittest.main()