import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Ensure the root directory is in python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.trigger_ingestion_agent import TriggerIngestionAgent, SEVERITY_RANK

class TestTriggerIngestionAgent(unittest.TestCase):

    def setUp(self):
        pass

    @patch('agents.trigger_ingestion_agent.GDACSAPIReader')
    def test_init_defaults(self, mock_reader):
        agent = TriggerIngestionAgent()
        self.assertEqual(agent.min_rank, 1)  # Default "Green" -> 1
        self.assertEqual(agent.max_results, 10)
        mock_reader.assert_called_once()

    @patch('agents.trigger_ingestion_agent.GDACSAPIReader')
    def test_init_custom(self, mock_reader):
        agent = TriggerIngestionAgent(min_alert_level="Red", max_results=5)
        self.assertEqual(agent.min_rank, 3)  # "Red" -> 3
        self.assertEqual(agent.max_results, 5)

        agent_orange = TriggerIngestionAgent(min_alert_level="Orange")
        self.assertEqual(agent_orange.min_rank, 2)  # "Orange" -> 2

        agent_invalid = TriggerIngestionAgent(min_alert_level="InvalidLevel")
        self.assertEqual(agent_invalid.min_rank, 1)  # Default fallback to 1

    @patch('agents.trigger_ingestion_agent.GDACSAPIReader')
    def test_fetch_success(self, mock_reader):
        mock_client = MagicMock()
        mock_reader.return_value = mock_client

        # Create mock features for latest_events
        feature_red = {
            "properties": {
                "eventid": 1,
                "episodeid": 1,
                "eventtype": "EQ",
                "name": "Red EQ",
                "country": "Country A",
                "iso3": "AAA",
                "affectedcountries": [{"countryname": "Country A"}],
                "alertlevel": "Red",
                "alertscore": 4.5,
                "severitydata": {"severity": "7.0", "severitytext": "Severe", "severityunit": "M"},
                "fromdate": "2026-07-02T10:00:00",
                "todate": "2026-07-03T10:00:00",
                "iscurrent": "true",
                "url": {"report": "http://red_report"},
                "source": "GDACS"
            },
            "geometry": {
                "coordinates": [100.0, 10.0]  # [lon, lat]
            }
        }

        feature_orange = {
            "properties": {
                "eventid": 2,
                "episodeid": 1,
                "eventtype": "TC",
                "name": "Orange TC",
                "country": "Country B",
                "iso3": "BBB",
                "affectedcountries": [],
                "alertlevel": "Orange",
                "alertscore": 2.5,
                "severitydata": {},
                "fromdate": "2026-07-01T10:00:00",
                "todate": "2026-07-03T10:00:00",
                "iscurrent": "false",
                "url": {},
                "source": "GDACS"
            },
            "geometry": {
                "coordinates": [105.0, 12.0]
            }
        }

        feature_green = {
            "properties": {
                "eventid": 3,
                "episodeid": 2,
                "eventtype": "FL",
                "name": "Green FL",
                "country": "Country C",
                "iso3": "CCC",
                "alertlevel": "Green",
                "fromdate": "2026-07-03T10:00:00"
            },
            "geometry": {
                "coordinates": [110.0, 15.0]
            }
        }

        mock_events = MagicMock()
        mock_events.features = [feature_orange, feature_red, feature_green]
        mock_client.latest_events.return_value = mock_events

        # Fetch with min_alert_level="Orange" (min_rank = 2)
        agent = TriggerIngestionAgent(min_alert_level="Orange")
        alerts = agent.fetch()

        # Should only contain Red and Orange alerts
        self.assertEqual(len(alerts), 2)
        # Should be sorted by alert_rank descending (Red first, then Orange)
        self.assertEqual(alerts[0]["event_id"], 1)
        self.assertEqual(alerts[0]["alert_level"], "Red")
        self.assertEqual(alerts[0]["lat"], 10.0)
        self.assertEqual(alerts[0]["lon"], 100.0)
        self.assertEqual(alerts[0]["is_current"], True)
        self.assertEqual(alerts[0]["affected"], ["Country A"])

        self.assertEqual(alerts[1]["event_id"], 2)
        self.assertEqual(alerts[1]["alert_level"], "Orange")
        self.assertEqual(alerts[1]["lat"], 12.0)
        self.assertEqual(alerts[1]["lon"], 105.0)
        self.assertEqual(alerts[1]["is_current"], False)
        self.assertEqual(alerts[1]["affected"], [])

    @patch('agents.trigger_ingestion_agent.GDACSAPIReader')
    def test_fetch_sorting_tiebreaker(self, mock_reader):
        mock_client = MagicMock()
        mock_reader.return_value = mock_client

        # Two alerts with the same alert_rank (Orange) but different dates
        feature_older = {
            "properties": {
                "eventid": 1,
                "alertlevel": "Orange",
                "fromdate": "2026-07-01T00:00:00"
            },
            "geometry": {
                "coordinates": [0.0, 0.0]
            }
        }
        feature_newer = {
            "properties": {
                "eventid": 2,
                "alertlevel": "Orange",
                "fromdate": "2026-07-02T00:00:00"
            },
            "geometry": {
                "coordinates": [0.0, 0.0]
            }
        }

        mock_events = MagicMock()
        mock_events.features = [feature_older, feature_newer]
        mock_client.latest_events.return_value = mock_events

        agent = TriggerIngestionAgent(min_alert_level="Green")
        alerts = agent.fetch()

        self.assertEqual(len(alerts), 2)
        # Sorted by alert_rank (same), then by from_date descending (newer first)
        self.assertEqual(alerts[0]["event_id"], 2)
        self.assertEqual(alerts[1]["event_id"], 1)

    @patch('agents.trigger_ingestion_agent.GDACSAPIReader')
    def test_fetch_max_results(self, mock_reader):
        mock_client = MagicMock()
        mock_reader.return_value = mock_client

        features = []
        for i in range(15):
            features.append({
                "properties": {
                    "eventid": i,
                    "alertlevel": "Red",
                    "fromdate": "2026-07-01T00:00:00"
                },
                "geometry": {
                    "coordinates": [0.0, 0.0]
                }
            })

        mock_events = MagicMock()
        mock_events.features = features
        mock_client.latest_events.return_value = mock_events

        agent = TriggerIngestionAgent(max_results=5)
        alerts = agent.fetch()

        self.assertEqual(len(alerts), 5)

    @patch('agents.trigger_ingestion_agent.GDACSAPIReader')
    def test_fetch_api_failure(self, mock_reader):
        mock_client = MagicMock()
        mock_reader.return_value = mock_client
        mock_client.latest_events.side_effect = Exception("Connection error")

        agent = TriggerIngestionAgent()
        alerts = agent.fetch()
        self.assertEqual(alerts, [])

    @patch('agents.trigger_ingestion_agent.GDACSAPIReader')
    def test_fetch_top(self, mock_reader):
        mock_client = MagicMock()
        mock_reader.return_value = mock_client

        feature = {
            "properties": {
                "eventid": 42,
                "alertlevel": "Red",
                "fromdate": "2026-07-01"
            },
            "geometry": {
                "coordinates": [0.0, 0.0]
            }
        }
        mock_events = MagicMock()
        mock_events.features = [feature]
        mock_client.latest_events.return_value = mock_events

        agent = TriggerIngestionAgent()
        top = agent.fetch_top()
        self.assertIsNotNone(top)
        self.assertEqual(top["event_id"], 42)

        # Empty case
        mock_events.features = []
        top_empty = agent.fetch_top()
        self.assertIsNone(top_empty)

    @patch('agents.trigger_ingestion_agent.GDACSAPIReader')
    def test_fetch_by_type(self, mock_reader):
        mock_client = MagicMock()
        mock_reader.return_value = mock_client

        f_tc = {
            "properties": {"eventid": 1, "alertlevel": "Red", "eventtype": "TC", "fromdate": "2026-07-01"},
            "geometry": {"coordinates": [0.0, 0.0]}
        }
        f_fl = {
            "properties": {"eventid": 2, "alertlevel": "Red", "eventtype": "FL", "fromdate": "2026-07-01"},
            "geometry": {"coordinates": [0.0, 0.0]}
        }

        mock_events = MagicMock()
        mock_events.features = [f_tc, f_fl]
        mock_client.latest_events.return_value = mock_events

        agent = TriggerIngestionAgent()
        tc_alerts = agent.fetch_by_type("TC")
        self.assertEqual(len(tc_alerts), 1)
        self.assertEqual(tc_alerts[0]["event_type"], "TC")

    @patch('agents.trigger_ingestion_agent.GDACSAPIReader')
    def test_parse_event_malformed(self, mock_reader):
        agent = TriggerIngestionAgent()

        # Missing properties
        malformed1 = {
            "geometry": {"coordinates": [1.0, 2.0]}
        }
        self.assertIsNone(agent._parse_event(malformed1))

        # Missing geometry
        malformed2 = {
            "properties": {"eventid": 1}
        }
        self.assertIsNone(agent._parse_event(malformed2))

        # Empty coordinates
        malformed3 = {
            "properties": {"eventid": 1},
            "geometry": {"coordinates": []}
        }
        self.assertIsNone(agent._parse_event(malformed3))

        # Coordinates is not a list/iterable of size >= 2
        malformed4 = {
            "properties": {"eventid": 1},
            "geometry": {"coordinates": None}
        }
        self.assertIsNone(agent._parse_event(malformed4))


if __name__ == '__main__':
    unittest.main()