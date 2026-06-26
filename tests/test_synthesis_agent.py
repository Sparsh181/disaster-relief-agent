import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.trigger_ingestion_agent    import TriggerIngestionAgent
from agents.weather_context_agent      import WeatherContextAgent
from agents.humanitarian_impact_agent  import HumanitarianImpactAgent
from agents.synthesis_output_agent     import SynthesisOutputAgent

trigger   = TriggerIngestionAgent(min_alert_level="Green", max_results=3)
weather   = WeatherContextAgent()
impact    = HumanitarianImpactAgent()
synthesis = SynthesisOutputAgent()

# Get top alert
alert_data   = trigger.fetch_top()
weather_data = weather.fetch_for_alert(alert_data)
impact_data  = impact.assess(alert_data, weather_data)
briefing     = synthesis.synthesize(alert_data, weather_data, impact_data)

# Print the plain text briefing
print("\n" + briefing["text"])

# Print structured keys (for API/DB use)
print("\n=== STRUCTURED KEYS ===")
print(json.dumps(briefing["structured"], indent=2)[:500] + "...")
print("\n=== METADATA ===")
print(json.dumps(briefing["metadata"], indent=2))

from agents.risk_reviewer_agent import RiskReviewerAgent

reviewer = RiskReviewerAgent()

print("\n\n=== REVIEWER AGENT TEST ===")
reviewed = reviewer.review(briefing)

print("\nREVIEW REPORT:")
print(json.dumps(reviewed["review_report"], indent=2))

print("\nFINAL BRIEFING TEXT (after review):")
print(reviewed["text"])