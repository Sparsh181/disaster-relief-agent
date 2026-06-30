#!/usr/bin/env python3
"""
Disaster Relief Agent — CLI
-----------------------------
Command-line interface for the disaster relief agent.
Covers the "Agent Skills (CLI)" rubric criterion.

Usage:
  python cli/briefing.py alerts                          # list live alerts
  python cli/briefing.py alerts --severity Orange         # filter by severity
  python cli/briefing.py brief --event-id 123 --type EQ   # get a briefing
  python cli/briefing.py brief --latest                   # brief the top alert
  python cli/briefing.py register                         # register for alerts
  python cli/briefing.py stats                            # system stats
  python cli/briefing.py run-once                         # run one scheduler cycle
  python cli/briefing.py serve                            # start the API server
"""

import sys
import os
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def cmd_alerts(args):
    """List live disaster alerts."""
    from mcp_server.tools import get_disaster_alerts

    result = get_disaster_alerts(
        min_severity=args.severity,
        event_type=args.type,
        max_results=args.limit
    )
    data = json.loads(result)

    if "error" in data:
        print(f"❌ Error: {data['error']}")
        return

    alerts = data.get("alerts", [])
    print(f"\n🌍 {len(alerts)} alerts found ({args.severity}+ severity)\n")
    print(f"{'LEVEL':8} {'TYPE':6} {'NAME':40} {'COUNTRY':20} SEVERITY")
    print("-" * 100)

    for a in alerts:
        level_icon = {"Red": "🔴", "Orange": "🟠", "Green": "🟢"}.get(a.get("alert_level"), "⚪")
        print(f"{level_icon} {a.get('alert_level','?'):6} "
              f"{a.get('event_type','?'):6} "
              f"{(a.get('name') or '')[:40]:40} "
              f"{(a.get('country') or '')[:20]:20} "
              f"{a.get('severity_text','')}")
        if args.verbose:
            print(f"         ID: {a.get('event_id')} | Lat/Lon: {a.get('lat')}, {a.get('lon')} | "
                  f"Report: {a.get('report_url')}")
    print()


def cmd_brief(args):
    """Get a full briefing for an event."""
    from mcp_server.tools import get_disaster_alerts, get_full_briefing
    from agents.trigger_ingestion_agent import TriggerIngestionAgent

    if args.latest:
        print("Fetching latest alert...")
        trigger = TriggerIngestionAgent(min_alert_level="Green", max_results=5)
        top = trigger.fetch_top()
        if not top:
            print("❌ No alerts found")
            return
        event_id   = top["event_id"]
        event_type = top["event_type"]
        print(f"Using top alert: {top['name']} ({top['alert_level']})")
    else:
        if not args.event_id or not args.type:
            print("❌ Provide --event-id and --type, or use --latest")
            return
        event_id   = args.event_id
        event_type = args.type

    print(f"\nGenerating briefing for {event_type}:{event_id}"
          f"{' (with LLM impact assessment)' if args.impact else ' (sensor data only)'}...\n")

    result = get_full_briefing(event_id, event_type, include_impact=args.impact)
    data   = json.loads(result)

    if "error" in data:
        print(f"❌ Error: {data['error']}")
        return

    print(data.get("briefing_text", "No briefing text"))

    if args.save:
        os.makedirs("data/processed", exist_ok=True)
        filename = f"data/processed/briefing_{event_type}_{event_id}.txt"
        with open(filename, "w") as f:
            f.write(data.get("briefing_text", ""))
        print(f"\n✅ Saved to {filename}")


def cmd_register(args):
    """Register for location-aware notifications."""
    from system.database import Database

    db = Database()
    db.init()

    name      = args.name or input("Name: ")
    email     = args.email or input("Email: ")
    lat       = args.lat if args.lat is not None else float(input("Latitude: "))
    lon       = args.lon if args.lon is not None else float(input("Longitude: "))
    radius    = args.radius
    min_alert = args.min_alert

    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        print("❌ Invalid latitude/longitude")
        return

    user_id = db.register_user(name, email, lat, lon, radius, min_alert)
    print(f"\n✅ Registered: {name} <{email}>")
    print(f"   Location  : {lat}, {lon}")
    print(f"   Radius    : {radius} km")
    print(f"   Min alert : {min_alert}")
    print(f"   User ID   : {user_id}")


def cmd_stats(args):
    """Show system statistics."""
    from system.database import Database

    db = Database()
    db.init()
    stats = db.get_stats()

    print("\n📊 SYSTEM STATISTICS")
    print("-" * 30)
    for key, value in stats.items():
        print(f"  {key.replace('_', ' ').title():25} {value}")
    print()


def cmd_run_once(args):
    """Run one scheduler cycle (fetch alerts, process, notify)."""
    from system.database import Database
    from system.scheduler import DisasterAgentScheduler

    db        = Database()
    db.init()
    scheduler = DisasterAgentScheduler(db, dry_run=args.dry_run)
    stats     = scheduler.run_cycle(include_impact=args.impact)

    print(f"\n✅ Cycle complete: {json.dumps(stats, indent=2)}")


def cmd_serve(args):
    """Start the FastAPI server."""
    import uvicorn
    print(f"🚀 Starting API server on port {args.port}...")
    uvicorn.run("api.main:app", host="0.0.0.0", port=args.port, reload=args.reload)


def main():
    parser = argparse.ArgumentParser(
        prog="briefing",
        description="🌍 Disaster Relief Agent — CLI for monitoring global disasters"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # alerts
    p_alerts = subparsers.add_parser("alerts", help="List live disaster alerts")
    p_alerts.add_argument("--severity", default="Green", choices=["Green", "Orange", "Red"])
    p_alerts.add_argument("--type", default="ALL", choices=["ALL","EQ","TC","FL","VO","WF","DR"])
    p_alerts.add_argument("--limit", type=int, default=10)
    p_alerts.add_argument("-v", "--verbose", action="store_true")
    p_alerts.set_defaults(func=cmd_alerts)

    # brief
    p_brief = subparsers.add_parser("brief", help="Generate a briefing for an event")
    p_brief.add_argument("--event-id", type=int)
    p_brief.add_argument("--type", choices=["EQ","TC","FL","VO","WF","DR"])
    p_brief.add_argument("--latest", action="store_true", help="Use the top current alert")
    p_brief.add_argument("--impact", action="store_true", help="Include LLM impact assessment (uses quota)")
    p_brief.add_argument("--save", action="store_true", help="Save briefing to file")
    p_brief.set_defaults(func=cmd_brief)

    # register
    p_register = subparsers.add_parser("register", help="Register for location-aware notifications")
    p_register.add_argument("--name")
    p_register.add_argument("--email")
    p_register.add_argument("--lat", type=float)
    p_register.add_argument("--lon", type=float)
    p_register.add_argument("--radius", type=float, default=500)
    p_register.add_argument("--min-alert", default="Orange", choices=["Green","Orange","Red"])
    p_register.set_defaults(func=cmd_register)

    # stats
    p_stats = subparsers.add_parser("stats", help="Show system statistics")
    p_stats.set_defaults(func=cmd_stats)

    # run-once
    p_run = subparsers.add_parser("run-once", help="Run one scheduler cycle")
    p_run.add_argument("--dry-run", action="store_true")
    p_run.add_argument("--impact", action="store_true")
    p_run.set_defaults(func=cmd_run_once)

    # serve
    p_serve = subparsers.add_parser("serve", help="Start the API server")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--reload", action="store_true")
    p_serve.set_defaults(func=cmd_serve)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()