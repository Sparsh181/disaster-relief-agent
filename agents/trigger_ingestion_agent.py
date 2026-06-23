"""
Trigger / Ingestion Agent
--------------------------
Polls the GDACS feed for the latest global disaster alerts,
filters by severity threshold, and returns clean structured
dicts ready for downstream agents to consume.

Severity priority order:
  1. Red alerts (any event type)
  2. Orange alerts (any event type)
  3. Green TC/FL (cyclones + floods even at low severity)
  4. All Green (fallback, lowest priority)
"""

from gdacs.api import GDACSAPIReader
from datetime import datetime

# ── constants ──────────────────────────────────────────────
SEVERITY_RANK = {"Red": 3, "Orange": 2, "Green": 1}

# Event types the agent monitors
WATCHED_TYPES = ["EQ", "TC", "FL", "VO", "WF", "DR"]

# High-priority event types even at Green level
HIGH_PRIORITY_TYPES = ["TC", "FL", "VO"]


class TriggerIngestionAgent:
    """
    Polls GDACS and returns a filtered, ranked list of
    disaster alerts as clean structured dictionaries.
    """

    def __init__(self, min_alert_level="Green", max_results=10):
        """
        Args:
            min_alert_level : minimum alert level to include
                              "Red" → only Red
                              "Orange" → Orange + Red
                              "Green" → all (default)
            max_results     : max number of alerts to return
        """
        self.client = GDACSAPIReader()
        self.min_rank = SEVERITY_RANK.get(min_alert_level, 1)
        self.max_results = max_results

    def fetch(self):
        """
        Main method — fetches + filters + ranks GDACS alerts.
        Returns a list of clean alert dicts, sorted by severity.
        """
        print(f"[TriggerAgent] Polling GDACS at {datetime.utcnow().isoformat()} UTC...")

        try:
            raw_events = self.client.latest_events()
        except Exception as e:
            print(f"[TriggerAgent] ERROR: Failed to fetch GDACS feed — {e}")
            return []

        alerts = []

        for event in raw_events.features:
            parsed = self._parse_event(event)
            if parsed is None:
                continue

            # Apply severity filter
            if parsed["alert_rank"] < self.min_rank:
                # Special case: always include high-priority types
                # even at Green (TC, FL, VO can be dangerous at Green)
                if not (parsed["event_type"] in HIGH_PRIORITY_TYPES
                        and parsed["alert_level"] == "Green"):
                    continue

            alerts.append(parsed)

        # Sort by severity rank (highest first), then by date (newest first)
        alerts.sort(key=lambda x: (x["alert_rank"], x["from_date"]), reverse=True)

        # Cap results
        alerts = alerts[:self.max_results]

        print(f"[TriggerAgent] Found {len(alerts)} alerts after filtering")
        return alerts

    def fetch_top(self):
        """
        Convenience method — returns only the single
        highest-priority alert. Used for testing.
        """
        alerts = self.fetch()
        return alerts[0] if alerts else None

    def fetch_by_type(self, event_type):
        """
        Returns filtered alerts for a specific event type.
        Args:
            event_type: "EQ", "TC", "FL", "VO", "WF", "DR"
        """
        all_alerts = self.fetch()
        return [a for a in all_alerts if a["event_type"] == event_type]

    # ── private helpers ────────────────────────────────────

    def _parse_event(self, raw_event):
        """
        Converts a raw GDACS feature dict into a clean,
        flat alert dict for downstream agents.
        Returns None if the event is malformed.
        """
        try:
            props  = raw_event["properties"]
            coords = raw_event["geometry"]["coordinates"]
            sev    = props.get("severitydata", {})

            return {
                # Identity
                "event_id"       : props.get("eventid"),
                "episode_id"     : props.get("episodeid"),
                "event_type"     : props.get("eventtype"),
                "name"           : props.get("name"),
                "country"        : props.get("country"),
                "iso3"           : props.get("iso3"),
                "affected"       : [
                    c["countryname"]
                    for c in props.get("affectedcountries", [])
                ],

                # Location (note: GDACS gives [lon, lat])
                "lat"            : coords[1],
                "lon"            : coords[0],

                # Severity
                "alert_level"    : props.get("alertlevel"),
                "alert_rank"     : SEVERITY_RANK.get(
                                     props.get("alertlevel"), 1),
                "alert_score"    : props.get("alertscore"),
                "severity_value" : sev.get("severity"),
                "severity_text"  : sev.get("severitytext"),
                "severity_unit"  : sev.get("severityunit"),

                # Timing
                "from_date"      : props.get("fromdate"),
                "to_date"        : props.get("todate"),
                "is_current"     : props.get("iscurrent") == "true",

                # Links
                "report_url"     : props.get("url", {}).get("report"),

                # Metadata
                "source"         : props.get("source"),
                "fetched_at"     : datetime.utcnow().isoformat()
            }

        except (KeyError, TypeError, IndexError) as e:
            print(f"[TriggerAgent] WARNING: Skipping malformed event — {e}")
            return None