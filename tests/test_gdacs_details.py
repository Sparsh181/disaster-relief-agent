import requests
import json
from gdacs.api import GDACSAPIReader

client = GDACSAPIReader()

# -------------------------------------------------------
# Test 1: EMM Media endpoint (different from eventnews)
# Using Typhoon MEKKHALA since it's our best current event
# -------------------------------------------------------
print("=== TEST 1: EMM MEDIA ENDPOINT (Typhoon MEKKHALA-26) ===")
emm_url = "https://www.gdacs.org/gdacsapi/api/emm/getemmnewsbykey?eventtype=TC&eventid=1001277"
emm_response = requests.get(emm_url)
emm_data = emm_response.json()
print(f"Status: {emm_response.status_code}")
print(f"Articles found: {len(emm_data) if isinstance(emm_data, list) else 'not a list'}")
print(json.dumps(emm_data, indent=2)[:1500] if emm_data else "Empty")

# -------------------------------------------------------
# Test 2: Historical significant event
# Vanuatu earthquake 2024 - known Orange/Red event
# eventtype=EQ, eventid=1360888
# -------------------------------------------------------
print("\n\n=== TEST 2: HISTORICAL ORANGE/RED EVENT ===")
print("(Vanuatu Earthquake 2024 - known significant event)")

hist_url = "https://www.gdacs.org/gdacsapi/api/events/geteventdata"
params = {
    "eventtype": "EQ",
    "eventid": "1360888"
}
response = requests.get(hist_url, params=params)
data = response.json()
props = data.get("properties", {})

print(f"""
    Name         : {props.get('name')}
    Country      : {props.get('country')}
    Alert Level  : {props.get('alertlevel')}
    Severity     : {props.get('severitydata', {}).get('severitytext')}
    Description  : {props.get('htmldescription')}
    Affected     : {[c['countryname'] for c in props.get('affectedcountries', [])]}
""")

# Episode detail for historical event
episodes = props.get("episodes", [])
if episodes:
    ep_url = episodes[0].get("details")
    print(f"Fetching episode detail: {ep_url}")
    ep_response = requests.get(ep_url)
    ep_props = ep_response.json().get("properties", {})
    print("\nEPISODE PROPS (full - looking for population/impact):")
    print(json.dumps(ep_props, indent=2)[:2000])

# EMM news for historical event
print("\nFetching EMM news for historical event...")
hist_emm = requests.get(
    "https://www.gdacs.org/gdacsapi/api/emm/getemmnewsbykey?eventtype=EQ&eventid=1360888"
)
hist_news = hist_emm.json()
print(f"Articles found: {len(hist_news) if isinstance(hist_news, list) else 'not a list'}")
if hist_news and isinstance(hist_news, list):
    for article in hist_news[:3]:
        print(f"\n  Title  : {article.get('title') or article.get('name') or list(article.keys())}")
        print(f"  Raw    : {json.dumps(article, indent=2)[:300]}")