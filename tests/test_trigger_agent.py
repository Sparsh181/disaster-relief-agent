import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.trigger_ingestion_agent import TriggerIngestionAgent

agent = TriggerIngestionAgent(min_alert_level="Green", max_results=10)

# Test 1: fetch all
print("=== ALL FILTERED ALERTS ===")
alerts = agent.fetch()
for a in alerts:
    print(f"  [{a['alert_level']:6}] {a['name']} | {a['country']} | {a['severity_text']}")

# Test 2: top alert only
print("\n=== TOP ALERT ===")
top = agent.fetch_top()
if top:
    print(f"  Name      : {top['name']}")
    print(f"  Country   : {top['country']}")
    print(f"  Level     : {top['alert_level']}")
    print(f"  Severity  : {top['severity_text']}")
    print(f"  Lat/Lon   : {top['lat']}, {top['lon']}")
    print(f"  Date      : {top['from_date']}")
    print(f"  Report    : {top['report_url']}")

# Test 3: only cyclones
print("\n=== CYCLONES ONLY ===")
cyclones = agent.fetch_by_type("TC")
for c in cyclones:
    print(f"  {c['name']} | {c['country']} | {c['alert_level']}")