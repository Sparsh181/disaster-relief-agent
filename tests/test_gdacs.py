from gdacs.api import GDACSAPIReader

client = GDACSAPIReader()

# --- Test 1: Get all recent events ---
print("=== ALL RECENT EVENTS ===")
events = client.latest_events()
for event in list(events.features)[:5]:
    props = event['properties']
    coords = event['geometry']['coordinates']
    severity = props.get('severitydata', {})
    print(f"""
    Type       : {props.get('eventtype')}
    Name       : {props.get('name')}
    Country    : {props.get('country')}
    Alert Level: {props.get('alertlevel')}
    Severity   : {severity.get('severitytext')}
    Date       : {props.get('fromdate')}
    Lat/Long   : {coords[1]}, {coords[0]}
    Report URL : {props.get('url', {}).get('report')}
    """)

# --- Test 2: Filter by event type ---
print("\n=== EARTHQUAKES ONLY ===")
eq_events = client.latest_events(event_type="EQ")
for event in list(eq_events.features)[:3]:
    props = event['properties']
    print(f"  {props.get('name')} | {props.get('alertlevel')} | {props.get('country')}")

print("\n=== FLOODS ONLY ===")
fl_events = client.latest_events(event_type="FL")
for event in list(fl_events.features)[:3]:
    props = event['properties']
    print(f"  {props.get('name')} | {props.get('alertlevel')} | {props.get('country')}")

print("\n=== TROPICAL CYCLONES ONLY ===")
tc_events = client.latest_events(event_type="TC")
for event in list(tc_events.features)[:3]:
    props = event['properties']
    print(f"  {props.get('name')} | {props.get('alertlevel')} | {props.get('country')}")

# --- Test 3: Filter Orange + Red alerts only (these are your agent triggers) ---
print("\n=== HIGH SEVERITY ALERTS (Orange + Red) ===")
all_events = client.latest_events()
high_severity = [
    e for e in all_events.features
    if e['properties'].get('alertlevel') in ['Orange', 'Red']
]
if high_severity:
    for event in high_severity[:5]:
        props = event['properties']
        print(f"  {props.get('name')} | {props.get('alertlevel')} | {props.get('country')} | {props.get('fromdate')}")
else:
    print("  No Orange/Red alerts right now (this is normal — run again later or lower threshold to Green)")