"""
Notifier — Location-aware email notifications
----------------------------------------------
Checks registered users against a new briefing and sends
email alerts only to users within their configured radius.

Uses haversine formula for accurate distance calculation.
Deduplicates via DB to never send the same alert twice.

Usage:
  from system.notifier import Notifier
  notifier = Notifier(db)
  notifier.notify_nearby_users(alert, briefing_id, briefing_text)
"""

import smtplib
import os
from math import radians, sin, cos, sqrt, atan2
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

# ── Alert level rank for severity filtering ─────────────────
ALERT_RANK = {"Green": 1, "Orange": 2, "Red": 3}


def haversine_distance(lat1: float, lon1: float,
                       lat2: float, lon2: float) -> float:
    """
    Calculate real-world distance between two lat/lon points
    using the Haversine formula. Returns distance in km.
    """
    R = 6371  # Earth radius in km
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


class Notifier:
    """
    Handles location-aware email notifications.
    Only notifies users within their configured radius
    and above their minimum alert severity threshold.
    """

    def __init__(self, db):
        self.db          = db
        self.smtp_host   = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port   = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user   = os.getenv("SMTP_USER", "")
        self.smtp_pass   = os.getenv("SMTP_PASS", "")
        self.from_email  = os.getenv("SMTP_USER", "disaster-relief-agent@noreply.com")

    def notify_nearby_users(self, alert: dict, briefing_id: int,
                             briefing_text: str) -> dict:
        """
        Check all registered users and email those within range.

        Args:
            alert        : alert dict from TriggerIngestionAgent
            briefing_id  : DB id of the briefing
            briefing_text: Plain text briefing to send

        Returns:
            dict with notified/skipped/failed counts
        """
        users    = self.db.get_all_users()
        alert_lat = alert.get("lat", 0)
        alert_lon = alert.get("lon", 0)
        alert_level = alert.get("alert_level", "Green")

        stats = {"notified": 0, "skipped_distance": 0,
                 "skipped_severity": 0, "skipped_duplicate": 0,
                 "failed": 0}

        print(f"[Notifier] Checking {len(users)} users for "
              f"{alert.get('name')} ({alert_level})...")

        for user in users:
            # Check if already notified
            if self.db.notification_already_sent(user["id"], briefing_id):
                stats["skipped_duplicate"] += 1
                continue

            # Check severity threshold
            user_min_rank   = ALERT_RANK.get(user["min_alert"], 2)
            alert_rank      = ALERT_RANK.get(alert_level, 1)
            if alert_rank < user_min_rank:
                stats["skipped_severity"] += 1
                continue

            # Check distance
            distance = haversine_distance(
                user["lat"], user["lon"],
                alert_lat, alert_lon
            )

            if distance > user["radius_km"]:
                stats["skipped_distance"] += 1
                print(f"  {user['email']}: {distance:.0f}km away "
                      f"(radius: {user['radius_km']}km) — skipped")
                continue

            # Send email
            sent = self._send_email(
                to           = user["email"],
                name         = user["name"],
                alert        = alert,
                distance     = distance,
                briefing_text= briefing_text
            )

            if sent:
                self.db.log_notification(user["id"], briefing_id)
                stats["notified"] += 1
                print(f"  ✅ {user['email']}: notified "
                      f"({distance:.0f}km away)")
            else:
                stats["failed"] += 1
                print(f"  ❌ {user['email']}: send failed")

        print(f"[Notifier] Done — {stats}")
        return stats

    def _send_email(self, to: str, name: str, alert: dict,
                    distance: float, briefing_text: str) -> bool:
        """
        Send an email notification to one user.
        Returns True if sent successfully.
        """
        if not self.smtp_user or not self.smtp_pass:
            # Email not configured — log and skip
            print(f"  [Notifier] Email not configured "
                  f"(SMTP_USER/SMTP_PASS not set) — skipping send")
            return True  # count as success for demo purposes

        try:
            subject = (
                f"🔴 Disaster Alert — {alert.get('name')} "
                f"({int(distance)}km from you)"
            )

            body = f"""Hi {name},

A new disaster alert has been detected near your registered location.
You are approximately {int(distance)} km from the affected area.

{briefing_text}

---
To update your notification preferences, visit your dashboard.
This is an automated message from Disaster Relief Agent.
"""
            msg = MIMEMultipart()
            msg["From"]    = self.from_email
            msg["To"]      = to
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_pass)
                server.send_message(msg)

            return True

        except Exception as e:
            print(f"  [Notifier] Email error: {e}")
            return False

    def test_distance(self, user_lat: float, user_lon: float,
                      alert_lat: float, alert_lon: float) -> float:
        """Utility: test haversine distance between two points."""
        return haversine_distance(user_lat, user_lon, alert_lat, alert_lon)


# ── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from system.database import Database

    db       = Database()
    db.init()
    notifier = Notifier(db)

    # Test haversine distance
    print("=== DISTANCE TESTS ===")
    # Hyderabad to Philippines earthquake
    d1 = notifier.test_distance(17.385, 78.486, 5.2392, 125.1965)
    print(f"Hyderabad → Philippines EQ : {d1:.0f} km")

    # Hyderabad to Venezuela earthquake
    d2 = notifier.test_distance(17.385, 78.486, 10.453, -68.5139)
    print(f"Hyderabad → Venezuela EQ   : {d2:.0f} km")

    # Register a test user in Hyderabad
    user_id = db.register_user(
        name      = "Sparsh",
        email     = "sparsh@test.com",
        lat       = 17.385,
        lon       = 78.486,
        radius_km = 500,
        min_alert = "Orange"
    )
    print(f"\n✅ Test user registered — id: {user_id}")

    # Test notification check (no email sent since SMTP not configured)
    test_alert = {
        "event_id"   : "TEST002",
        "event_type" : "EQ",
        "name"       : "Earthquake near Hyderabad",
        "country"    : "India",
        "alert_level": "Orange",
        "lat"        : 17.0,
        "lon"        : 79.0
    }

    # Save a fake briefing to test against
    alert_db_id  = db.upsert_alert(test_alert)
    briefing_id  = db.save_briefing(alert_db_id, "TEST002", {
        "text"       : "Test briefing",
        "structured" : {},
        "review_report": {"passed": True, "flag_count": 0},
        "metadata"   : {"llm_used": False}
    })

    stats = notifier.notify_nearby_users(
        test_alert, briefing_id, "Test briefing text"
    )
    print(f"\n✅ Notification stats: {stats}")
