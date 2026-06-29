"""
Database Layer — SQLite
------------------------
Handles all persistent storage for the disaster relief agent.

Tables:
  - alerts          : all disaster alerts seen by the system
  - briefings       : generated briefings per alert
  - users           : registered users for notifications
  - notifications   : log of sent notifications (deduplication)

All queries use parameterized statements to prevent SQL injection.

Usage:
  from system.database import Database
  db = Database()
  db.init()
"""

import sqlite3
import json
import os
from datetime import datetime, timezone

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "disaster_relief.db"
)


class Database:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # return dicts instead of tuples
        conn.execute("PRAGMA journal_mode=WAL")  # better concurrency
        return conn

    # ══════════════════════════════════════════════════════
    # INIT — create tables if they don't exist
    # ══════════════════════════════════════════════════════
    def init(self):
        """Create all tables. Safe to call multiple times."""
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id    TEXT NOT NULL,
                    event_type  TEXT NOT NULL,
                    name        TEXT,
                    country     TEXT,
                    alert_level TEXT,
                    severity    TEXT,
                    lat         REAL,
                    lon         REAL,
                    from_date   TEXT,
                    report_url  TEXT,
                    raw_json    TEXT,
                    seen_at     TEXT NOT NULL,
                    UNIQUE(event_id, event_type)
                );

                CREATE TABLE IF NOT EXISTS briefings (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    alert_id     INTEGER NOT NULL,
                    event_id     TEXT NOT NULL,
                    briefing_text TEXT,
                    structured   TEXT,
                    review_passed INTEGER,
                    review_flags  INTEGER,
                    llm_used      INTEGER,
                    generated_at  TEXT NOT NULL,
                    FOREIGN KEY(alert_id) REFERENCES alerts(id)
                );

                CREATE TABLE IF NOT EXISTS users (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    name       TEXT NOT NULL,
                    email      TEXT NOT NULL UNIQUE,
                    lat        REAL NOT NULL,
                    lon        REAL NOT NULL,
                    radius_km  REAL DEFAULT 500,
                    min_alert  TEXT DEFAULT 'Orange',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS notifications (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id    INTEGER NOT NULL,
                    briefing_id INTEGER NOT NULL,
                    sent_at    TEXT NOT NULL,
                    UNIQUE(user_id, briefing_id),
                    FOREIGN KEY(user_id) REFERENCES users(id),
                    FOREIGN KEY(briefing_id) REFERENCES briefings(id)
                );
            """)
        print(f"[DB] Initialized → {self.db_path}")

    # ══════════════════════════════════════════════════════
    # ALERTS
    # ══════════════════════════════════════════════════════
    def upsert_alert(self, alert: dict) -> int:
        """
        Insert alert if new, ignore if already seen.
        Returns the alert's DB row id.
        """
        with self._connect() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO alerts
                (event_id, event_type, name, country, alert_level,
                 severity, lat, lon, from_date, report_url, raw_json, seen_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                str(alert.get("event_id")),
                alert.get("event_type"),
                alert.get("name"),
                alert.get("country"),
                alert.get("alert_level"),
                alert.get("severity_text"),
                alert.get("lat"),
                alert.get("lon"),
                alert.get("from_date"),
                alert.get("report_url"),
                json.dumps(alert, default=str),
                datetime.now(timezone.utc).isoformat()
            ))

            row = conn.execute("""
                SELECT id FROM alerts
                WHERE event_id=? AND event_type=?
            """, (str(alert.get("event_id")), alert.get("event_type"))
            ).fetchone()

            return row["id"] if row else None

    def get_alert(self, event_id: str, event_type: str) -> dict:
        """Fetch a single alert by event_id + event_type."""
        with self._connect() as conn:
            row = conn.execute("""
                SELECT * FROM alerts WHERE event_id=? AND event_type=?
            """, (str(event_id), event_type)).fetchone()
            return dict(row) if row else None

    def get_recent_alerts(self, limit: int = 20) -> list:
        """Fetch most recent alerts."""
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT * FROM alerts ORDER BY seen_at DESC LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]

    def is_new_alert(self, event_id: str, event_type: str) -> bool:
        """Returns True if this alert hasn't been seen before."""
        return self.get_alert(event_id, event_type) is None

    # ══════════════════════════════════════════════════════
    # BRIEFINGS
    # ══════════════════════════════════════════════════════
    def save_briefing(self, alert_id: int, event_id: str,
                      briefing: dict) -> int:
        """Save a generated briefing. Returns briefing DB id."""
        review = briefing.get("review_report", {})
        meta   = briefing.get("metadata", {})

        with self._connect() as conn:
            cursor = conn.execute("""
                INSERT INTO briefings
                (alert_id, event_id, briefing_text, structured,
                 review_passed, review_flags, llm_used, generated_at)
                VALUES (?,?,?,?,?,?,?,?)
            """, (
                alert_id,
                str(event_id),
                briefing.get("text"),
                json.dumps(briefing.get("structured"), default=str),
                int(review.get("passed", True)),
                review.get("flag_count", 0),
                int(meta.get("llm_used", False)),
                datetime.now(timezone.utc).isoformat()
            ))
            return cursor.lastrowid

    def get_briefing(self, event_id: str) -> dict:
        """Fetch the latest briefing for an event."""
        with self._connect() as conn:
            row = conn.execute("""
                SELECT * FROM briefings WHERE event_id=?
                ORDER BY generated_at DESC LIMIT 1
            """, (str(event_id),)).fetchone()
            return dict(row) if row else None

    def get_recent_briefings(self, limit: int = 10) -> list:
        """Fetch most recent briefings with alert info joined."""
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT b.*, a.name, a.country, a.alert_level,
                       a.lat, a.lon, a.event_type
                FROM briefings b
                JOIN alerts a ON b.alert_id = a.id
                ORDER BY b.generated_at DESC LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]

    # ══════════════════════════════════════════════════════
    # USERS
    # ══════════════════════════════════════════════════════
    def register_user(self, name: str, email: str, lat: float,
                      lon: float, radius_km: float = 500,
                      min_alert: str = "Orange") -> int:
        """Register a new user. Returns user id."""
        # Validate min_alert
        if min_alert not in ["Green", "Orange", "Red"]:
            min_alert = "Orange"

        with self._connect() as conn:
            try:
                cursor = conn.execute("""
                    INSERT INTO users
                    (name, email, lat, lon, radius_km, min_alert, created_at)
                    VALUES (?,?,?,?,?,?,?)
                """, (
                    name, email, lat, lon, radius_km, min_alert,
                    datetime.now(timezone.utc).isoformat()
                ))
                return cursor.lastrowid
            except sqlite3.IntegrityError:
                # Email already exists — update instead
                conn.execute("""
                    UPDATE users SET name=?, lat=?, lon=?,
                    radius_km=?, min_alert=? WHERE email=?
                """, (name, lat, lon, radius_km, min_alert, email))
                row = conn.execute(
                    "SELECT id FROM users WHERE email=?", (email,)
                ).fetchone()
                return row["id"] if row else None

    def get_all_users(self) -> list:
        """Fetch all registered users."""
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM users").fetchall()
            return [dict(r) for r in rows]

    def get_user(self, email: str) -> dict:
        """Fetch a user by email."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE email=?", (email,)
            ).fetchone()
            return dict(row) if row else None

    # ══════════════════════════════════════════════════════
    # NOTIFICATIONS
    # ══════════════════════════════════════════════════════
    def log_notification(self, user_id: int, briefing_id: int) -> bool:
        """Log that a notification was sent. Returns False if duplicate."""
        with self._connect() as conn:
            try:
                conn.execute("""
                    INSERT INTO notifications (user_id, briefing_id, sent_at)
                    VALUES (?,?,?)
                """, (user_id, briefing_id,
                      datetime.now(timezone.utc).isoformat()))
                return True
            except sqlite3.IntegrityError:
                return False  # already sent

    def notification_already_sent(self, user_id: int,
                                   briefing_id: int) -> bool:
        """Check if notification was already sent to this user."""
        with self._connect() as conn:
            row = conn.execute("""
                SELECT id FROM notifications
                WHERE user_id=? AND briefing_id=?
            """, (user_id, briefing_id)).fetchone()
            return row is not None

    # ══════════════════════════════════════════════════════
    # STATS (for dashboard + eval)
    # ══════════════════════════════════════════════════════
    def get_stats(self) -> dict:
        """Returns summary stats for dashboard display."""
        with self._connect() as conn:
            return {
                "total_alerts"   : conn.execute(
                    "SELECT COUNT(*) FROM alerts").fetchone()[0],
                "total_briefings": conn.execute(
                    "SELECT COUNT(*) FROM briefings").fetchone()[0],
                "total_users"    : conn.execute(
                    "SELECT COUNT(*) FROM users").fetchone()[0],
                "notifications_sent": conn.execute(
                    "SELECT COUNT(*) FROM notifications").fetchone()[0],
                "red_alerts"     : conn.execute(
                    "SELECT COUNT(*) FROM alerts WHERE alert_level='Red'"
                ).fetchone()[0],
                "orange_alerts"  : conn.execute(
                    "SELECT COUNT(*) FROM alerts WHERE alert_level='Orange'"
                ).fetchone()[0],
            }


# ── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    db = Database()
    db.init()

    # Test alert upsert
    test_alert = {
        "event_id"   : "TEST001",
        "event_type" : "EQ",
        "name"       : "Test Earthquake",
        "country"    : "TestLand",
        "alert_level": "Orange",
        "severity_text": "Magnitude 6.0M",
        "lat"        : 10.0,
        "lon"        : 20.0,
        "from_date"  : datetime.now(timezone.utc).isoformat(),
        "report_url" : "https://example.com"
    }

    alert_id = db.upsert_alert(test_alert)
    print(f"✅ Alert saved — id: {alert_id}")
    print(f"✅ Is new alert: {db.is_new_alert('TEST001', 'EQ')}")

    # Test user registration
    user_id = db.register_user(
        name="Test User", email="test@test.com",
        lat=10.5, lon=20.5, radius_km=300, min_alert="Orange"
    )
    print(f"✅ User registered — id: {user_id}")

    # Test stats
    print(f"✅ Stats: {db.get_stats()}")
    print("\n✅ All database tests passed!")
